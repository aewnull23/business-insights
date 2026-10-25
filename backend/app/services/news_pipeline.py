import re

from app.services.classify import classify_topics
from app.textutil import jaccard, tokens

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def extract_facts(item: dict) -> list[dict]:
    text = item.get("summary") or item.get("title") or ""
    sentences = [part.strip() for part in SENTENCE_RE.split(text) if len(part.strip()) > 20]
    facts = []
    for index, sentence in enumerate(sentences[:3], start=1):
        facts.append(
            {
                "id": f"{item['id']}-x{index}",
                "text": sentence,
                "verification": "unverified",
            }
        )
    if not facts and item.get("title"):
        facts.append(
            {
                "id": f"{item['id']}-x1",
                "text": item["title"],
                "verification": "unverified",
            }
        )
    return facts


def prepare_item(item: dict) -> dict:
    prepared = dict(item)
    blob = f"{item.get('title', '')}. {item.get('summary', '')}"
    prepared["topics"] = classify_topics(blob, item.get("topics") or None)
    prepared["facts"] = item.get("facts") or extract_facts(item)
    prepared["regions"] = item.get("regions") or []
    prepared["signals"] = extract_signals(blob, prepared["topics"])
    prepared["signals"].update(item.get("signals") or {})
    return prepared


def extract_signals(text: str, topics: list[str]) -> dict:
    """Extract only explicit rate decisions; forecasts and negation stay unknown."""
    if 'key_rate' not in topics:
        return {}
    normalized = text.lower().replace('ё', 'е')
    markers = {
        'unchanged': r'сохранил\w* ключев\w* ставк|ключев\w* ставк\w*[^.!?]{0,25}(?:без изменен|не измен|сохранен)',
        'hike': r'(?<!не )повысил\w* ключев\w* ставк|ключев\w* ставк\w*[^.!?]{0,20}повышена',
        'cut': r'(?<!не )снизил\w* ключев\w* ставк|ключев\w* ставк\w*[^.!?]{0,20}снижена',
    }
    directions = [key for key, pattern in markers.items() if re.search(pattern, normalized)]
    if len(directions) != 1:
        return {'key_rate': 'unknown'}
    return {'key_rate': directions[0]}


def deduplicate(items: list[dict]) -> tuple[list[dict], list[dict]]:
    ordered = sorted(items, key=lambda item: (len(item.get("facts") or []), item.get("published_at") or ""), reverse=True)
    kept: list[dict] = []
    dropped: list[dict] = []
    for item in ordered:
        twin = next(
            (
                current
                for current in kept
                if jaccard(tokens(current["title"]), tokens(item["title"])) >= 0.7
            ),
            None,
        )
        if twin:
            dropped.append({"dropped_id": item["id"], "kept_id": twin["id"]})
        else:
            kept.append(item)
    return kept, dropped
