import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


class Store:
    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self._init()

    def _init(self) -> None:
        with self.lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS analyses (
                    company_id TEXT NOT NULL,
                    news_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (company_id, news_id, version)
                );
                CREATE TABLE IF NOT EXISTS questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id TEXT NOT NULL,
                    news_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tool_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    company_id TEXT,
                    news_id TEXT,
                    status TEXT NOT NULL,
                    user_id TEXT
                );
                """
            )
            self.conn.commit()

    def save_run(self, run_id: str, company_id: str, payload: dict) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO runs (id, company_id, created_at, payload) VALUES (?, ?, ?, ?)",
                (run_id, company_id, _now(), json.dumps(payload, ensure_ascii=False)),
            )
            self.conn.commit()

    def save_analysis(self, company_id: str, news_id: str, version: str, payload: dict) -> None:
        with self.lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO analyses (company_id, news_id, version, payload, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (company_id, news_id, version, json.dumps(payload, ensure_ascii=False), _now()),
            )
            self.conn.commit()

    def get_analysis(self, company_id: str, news_id: str, version: str) -> dict | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT payload FROM analyses WHERE company_id = ? AND news_id = ? AND version = ?",
                (company_id, news_id, version),
            ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["payload"])
        except json.JSONDecodeError:
            return None

    def save_question(self, company_id: str, news_id: str, question: str, answer: dict) -> None:
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO questions (company_id, news_id, question, answer_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (company_id, news_id, question[:500], json.dumps(answer, ensure_ascii=False), _now()),
            )
            self.conn.commit()

    def add_audit(
        self,
        tool: str,
        company_id: str | None,
        news_id: str | None,
        status: str,
        user_id: str | None = None,
    ) -> None:
        with self.lock:
            columns = {row[1] for row in self.conn.execute("PRAGMA table_info(tool_audit)").fetchall()}
            if "user_id" not in columns:
                self.conn.execute("ALTER TABLE tool_audit ADD COLUMN user_id TEXT")
            self.conn.execute(
                "INSERT INTO tool_audit (ts, tool, company_id, news_id, status, user_id) VALUES (?, ?, ?, ?, ?, ?)",
                (_now(), tool, company_id, news_id, status, user_id),
            )
            self.conn.commit()

    def metrics(self) -> dict:
        with self.lock:
            tools = self.conn.execute(
                "SELECT tool, status, COUNT(*) AS n FROM tool_audit GROUP BY tool, status"
            ).fetchall()
            questions = self.conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
            analyses = self.conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
            runs = self.conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        return {
            "runs": runs,
            "analyses": analyses,
            "questions": questions,
            "tool_calls": [
                {"tool": row["tool"], "status": row["status"], "count": row["n"]} for row in tools
            ],
        }

    def close(self) -> None:
        with self.lock:
            self.conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_STORE: Store | None = None
_PATH: str | None = None


def get_store() -> Store:
    from app.config import settings

    global _STORE, _PATH
    path = settings().database_path
    if _STORE is None or _PATH != path:
        if _STORE is not None:
            _STORE.close()
        _STORE = Store(path)
        _PATH = path
    return _STORE


def reset_store() -> None:
    global _STORE, _PATH
    if _STORE is not None:
        _STORE.close()
    _STORE = None
    _PATH = None
