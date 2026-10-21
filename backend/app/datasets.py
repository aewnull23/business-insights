import json
from functools import lru_cache

from app.config import DATA_DIR
from app.schemas import Company, Document, NewsItem


def _read(name: str) -> list:
    path = DATA_DIR / name
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"{name} должен быть списком")
    return data


def _unique(ids: list[str], label: str) -> None:
    if len(ids) != len(set(ids)):
        raise ValueError(f"Повторяющиеся идентификаторы в {label}")


@lru_cache(maxsize=1)
def load_companies() -> tuple[dict, ...]:
    rows = [Company.model_validate(item).model_dump() for item in _read("companies.json")]
    _unique([row["id"] for row in rows], "компаниях")
    return tuple(rows)


@lru_cache(maxsize=1)
def load_news_seed() -> tuple[dict, ...]:
    rows = [NewsItem.model_validate(item).model_dump() for item in _read("news.json")]
    _unique([row["id"] for row in rows], "новостях")
    return tuple(rows)


@lru_cache(maxsize=1)
def load_documents() -> tuple[dict, ...]:
    rows = [Document.model_validate(item).model_dump() for item in _read("documents.json")]
    _unique([row["id"] for row in rows], "документах")
    return tuple(rows)


def clear_caches() -> None:
    load_companies.cache_clear()
    load_news_seed.cache_clear()
    load_documents.cache_clear()
