import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
DATA_DIR = BACKEND_ROOT / "data"
ANALYSIS_VERSION = "3"
LARGE_BUSINESS_REVENUE = 15_000_000_000

ALLOWED_MODELS = {
    "gemma 4 26b a4b",
    "gemma-4-26b-a4b",
    "glm-5.3-flash",
    "qwen3.6 35b a3b",
    "qwen3.6-35b-a3b",
    "deepseek-v4.1-flash",
    "qwen3-vl-30b-a3b-instruct",
    "kimi-k2.6",
}


def _clean(value: str | None) -> str:
    return (value or "").strip()


class Settings:
    def __init__(self) -> None:
        self.app_env = _clean(os.environ.get("APP_ENV")) or "demo"
        self.log_level = _clean(os.environ.get("LOG_LEVEL")) or "INFO"
        self.llm_base_url = _clean(os.environ.get("LLM_BASE_URL")).rstrip("/")
        self.llm_api_key = _clean(os.environ.get("LLM_API_KEY"))
        self.llm_model = _clean(os.environ.get("LLM_MODEL"))
        self.llm_max_calls = int(os.environ.get("LLM_MAX_CALLS") or "8")
        self.news_feed_urls = [
            item.strip()
            for item in _clean(os.environ.get("NEWS_FEED_URLS")).split(",")
            if item.strip()
        ]
        custom_db = _clean(os.environ.get("DATABASE_PATH"))
        self.database_path = custom_db or str(BACKEND_ROOT / "runtime" / "insights.sqlite")
        frontend = _clean(os.environ.get("FRONTEND_DIR"))
        self.frontend_dir = frontend or str(PROJECT_ROOT / "frontend")


def settings() -> Settings:
    return Settings()
