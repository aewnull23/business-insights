import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.sqlite"))
    monkeypatch.setenv("NEWS_FEED_URLS", "")
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_MODEL", "")
    from app.sources.feed import reset_news_cache
    from app.storage.store import reset_store

    reset_news_cache()
    reset_store()
    yield
    reset_news_cache()
    reset_store()
