import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from app.config import settings
from app.datasets import load_news_seed
from app.services.news_pipeline import deduplicate, prepare_item

_CACHE: dict = {"at": 0.0, "key": None, "items": None, "dropped": None, "rss_error": None}
TTL_SECONDS = 120


def parse_rss(payload: bytes | str) -> list[dict]:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    root = ET.fromstring(payload)
    items = []
    for node in root.iter():
        if _local(node.tag) != "item":
            continue
        title = _child_text(node, "title")
        if not title:
            continue
        link = _child_text(node, "link")
        description = _strip(_child_text(node, "description"))[:2000]
        published = _date(_child_text(node, "pubDate"))
        if not published:
            continue
        items.append(
            {
                "id": f"rss-{len(items) + 1}-{published}",
                "title": title.strip(),
                "published_at": published,
                "category": "Внешняя лента",
                "origin": "rss",
                "demo": False,
                "source_name": "RSS-лента",
                "source_url": link or None,
                "summary": description,
                "topics": [],
                "regions": [],
                "signals": {},
                "facts": [],
            }
        )
        if len(items) >= 20:
            break
    return items


def fetch_rss(url: str) -> list[dict]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.username:
        raise ValueError("unsupported url")
    request = urllib.request.Request(url, headers={"User-Agent": "business-insights-demo/0.1"})
    with urllib.request.urlopen(request, timeout=5) as response:
        payload = response.read(1_000_000)
    return parse_rss(payload)


def collect_news(force: bool = False) -> tuple[list[dict], list[dict], str | None]:
    config = settings()
    key = tuple(config.news_feed_urls)
    now = time.time()
    if (
        not force
        and _CACHE["items"] is not None
        and _CACHE["key"] == key
        and now - _CACHE["at"] < TTL_SECONDS
    ):
        return _CACHE["items"], _CACHE["dropped"], _CACHE["rss_error"]

    items = [prepare_item(dict(row)) for row in load_news_seed()]
    rss_error = None
    for url in config.news_feed_urls:
        try:
            for entry in fetch_rss(url):
                items.append(prepare_item(entry))
        except Exception as exc:
            rss_error = type(exc).__name__
    unique, dropped = deduplicate(items)
    _CACHE.update(at=now, key=key, items=unique, dropped=dropped, rss_error=rss_error)
    return unique, dropped, rss_error


def reset_news_cache() -> None:
    _CACHE.update(at=0.0, key=None, items=None, dropped=None, rss_error=None)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(node: ET.Element, name: str) -> str:
    for child in list(node):
        if _local(child.tag) == name and child.text:
            return child.text
    return ""


def _strip(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", value).split())


def _date(value: str) -> str:
    if not value:
        return ""
    if len(value) >= 10 and value[4] == "-" and value[7] == "-":
        return value[:10]
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return ""
