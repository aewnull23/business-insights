import re
import hashlib
import html
import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime
from urllib.parse import urljoin, urlparse

from app.config import settings
from app.datasets import load_news_seed
from app.services.news_pipeline import deduplicate, prepare_item

_CACHE: dict = {"at": 0.0, "key": None, "items": None, "dropped": None, "rss_error": None}
TTL_SECONDS = 120
MAX_FEED_BYTES = 1_000_000
MAX_ITEMS = 20


def parse_rss(payload: bytes | str, source_url: str | None = None) -> list[dict]:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    if len(payload) > MAX_FEED_BYTES:
        raise ValueError("Feed exceeds size limit")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("DTD and entity declarations are not allowed in feeds")
    root = ET.fromstring(payload)
    items = []
    seen = set()
    channel = next((node for node in root.iter() if _local(node.tag) in {"channel", "feed"}), root)
    source_name = _strip(_child_text(channel, "title"))[:200] or "RSS / Atom"
    for node in root.iter():
        kind = _local(node.tag)
        if kind not in {"item", "entry"}:
            continue
        title = _strip(_child_text(node, "title"))[:500]
        if not title:
            continue
        link = _child_text(node, "link").strip()
        if kind == "entry":
            link = next((child.get("href", "") for child in node
                         if _local(child.tag) == "link" and child.get("rel", "alternate") == "alternate"), "")
        link = urljoin(source_url or "", link)
        parsed_link = urlparse(link)
        if parsed_link.scheme not in {"http", "https"} or not parsed_link.hostname or parsed_link.username or parsed_link.password:
            link = ""
        description = _strip(_child_text(node, "description") or _child_text(node, "summary") or _child_text(node, "content"))[:2000]
        published = _date(_child_text(node, "pubDate") or _child_text(node, "published") or _child_text(node, "updated") or _child_text(node, "date"))
        if not published:
            continue
        # Independent of feed position: equally dated entries from separate
        # feeds cannot overwrite one another in persisted analyses.
        identity = json.dumps([link, title, published, description], ensure_ascii=False, separators=(",", ":"))
        item_id = "rss-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        if item_id in seen:
            continue
        seen.add(item_id)
        items.append(
            {
                "id": item_id,
                "title": title.strip(),
                "published_at": published,
                "category": "Внешняя лента",
                "origin": "rss",
                "demo": False,
                "source_name": source_name,
                "source_url": link or None,
                "summary": description,
                "topics": [],
                "regions": [],
                "signals": {},
                "facts": [],
            }
        )
        if len(items) >= MAX_ITEMS:
            break
    return items


def fetch_rss(url: str) -> list[dict]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("unsupported url")
    request = urllib.request.Request(url, headers={"User-Agent": "business-insights-demo/0.1"})
    with urllib.request.urlopen(request, timeout=5) as response:
        payload = response.read(MAX_FEED_BYTES + 1)
    return parse_rss(payload, source_url=url)


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
    errors = []
    for url in config.news_feed_urls:
        try:
            for entry in fetch_rss(url):
                items.append(prepare_item(entry))
        except Exception as exc:
            errors.append(f"{urlparse(url).hostname or 'feed'}: {type(exc).__name__}")
    rss_error = "; ".join(errors) or None
    unique, dropped = deduplicate(items)
    _CACHE.update(at=now, key=key, items=unique, dropped=dropped, rss_error=rss_error)
    return unique, dropped, rss_error


def reset_news_cache() -> None:
    _CACHE.update(at=0.0, key=None, items=None, dropped=None, rss_error=None)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(node: ET.Element, name: str) -> str:
    for child in list(node):
        if _local(child.tag) == name:
            return "".join(child.itertext())
    return ""


def _strip(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html.unescape(value)).split())


def _date(value: str) -> str:
    if not value:
        return ""
    try:
        if len(value) >= 10 and value[4] == "-" and value[7] == "-":
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return ""
