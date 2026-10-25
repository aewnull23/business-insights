import re
from datetime import date

from app.textutil import tokens


def _excerpt(text: str, query: set[str], limit: int = 800) -> str:
    if len(text) <= limit:
        return text.strip()
    # Keep a contiguous source passage around relevant sentences instead of
    # ranking a whole page but always returning its unrelated first 800 chars.
    starts = [0] + [match.end() for match in re.finditer(r'(?<=[.!?])\s+', text)]
    candidates = []
    for start in starts:
        candidate = text[start:start + limit]
        if start + limit < len(text):
            boundary = candidate.rfind(' ')
            candidate = candidate[:boundary] if boundary > 0 else candidate
        candidates.append((len(tokens(candidate) & query), -start, candidate.strip()))
    return max(candidates)[2]


def _same_subject(news: dict, text: str) -> bool:
    query = (news.get('title', '') + ' ' + news.get('summary', '')).lower()
    body = text.lower()
    russian_rate = re.search(r'ключев\w* ставк|банк\w* росси|цб\s*рф', query)
    if russian_rate and re.search(r'фрс|federal reserve', body) and not re.search(r'ключев\w* ставк|цб|росси', body):
        return False
    if re.search(r'сталь|стали|прокат|металлург', query) and re.search(r'золот|gold', body) and not re.search(r'сталь|стали|прокат|металлург', body):
        return False
    return True


def search_documents(news: dict, documents: list[dict], limit: int = 3, *, strategy: str = "topics") -> list[dict]:
    """Search labelled topics first; lexical retry also searches unlabelled excerpts."""
    if strategy not in {"topics", "lexical"}:
        raise ValueError("unknown retrieval strategy")
    news_topics = set(news.get("topics") or [])
    query = tokens(
        " ".join(
            [news.get("title") or "", news.get("summary") or ""]
            + [fact.get("text") or "" for fact in news.get("facts") or []]
        )
    )
    found = []
    for document in documents:
        if document.get("extraction_status") in {"ocr_required", "extraction_error", "metadata_only"}:
            continue
        published = document.get('published_at')
        event_date = news.get('published_at')
        historical = False
        if published and event_date:
            try:
                age = (date.fromisoformat(event_date[:10]) - date.fromisoformat(published[:10])).days
                if age < 0:
                    continue
                historical = age > 366
            except ValueError:
                pass
        shared = news_topics.intersection(document.get("topics") or [])
        if strategy == "topics" and not shared:
            continue
        paragraphs = [part.strip() for part in (document.get("text") or "").split("\n\n") if part.strip()]
        best_text = paragraphs[0] if paragraphs else (document.get("text") or "")
        best_score = -1
        for paragraph in paragraphs or [best_text]:
            score = len(tokens(paragraph) & query)
            if score > best_score:
                best_score = score
                best_text = paragraph
        # A retry must have evidence in the excerpt, not merely a broad profile match.
        if strategy == "lexical" and (best_score < 2 or best_score / max(len(query), 1) < 0.15):
            continue
        if not best_text.strip():
            continue
        excerpt = _excerpt(best_text, query)
        if not _same_subject(news, excerpt):
            continue
        legal_markers = re.findall(r'инвестиционн\w* рекомендац|информационн\w* цел|не нес[её]т ответственност|копировани|воспроизводств|генеральн\w* лицензи', excerpt, re.I)
        if len(legal_markers) >= 2:
            continue
        found.append(
            {
                "id": document["id"],
                "title": document["title"],
                "origin": document.get("origin"),
                "is_bank_research": bool(document.get("is_bank_research")),
                "source_url": document.get("source_url"),
                "excerpt": excerpt,
                "published_at": published,
                "historical": historical,
                "overlap": len(shared),
                "lexical_score": best_score,
                "topics": list(document.get("topics") or []),
                "strategy": strategy,
                **{key: document.get(key) for key in ("source_file", "page_start", "page_end", "extraction_status", "document_id")},
            }
        )
    found.sort(key=lambda item: (not item["is_bank_research"], -item["overlap"], -item["lexical_score"], item["id"]))
    # Multiple chunks of one PDF are a single source, not independent support.
    selected = []
    seen = set()
    for item in found:
        source = item.get('document_id') or item['id']
        if source in seen:
            continue
        seen.add(source)
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


BANK_ABSENT = (
    "Подходящий материал аналитики Альфа-Банка не найден. "
    "Демонстрационные справки, если они показаны отдельно, не являются позицией банка и не подменяют ее."
)
