from app.textutil import tokens


def search_documents(news: dict, documents: list[dict], limit: int = 3) -> list[dict]:
    news_topics = set(news.get("topics") or [])
    query = tokens(
        " ".join(
            [news.get("title") or "", news.get("summary") or ""]
            + [fact.get("text") or "" for fact in news.get("facts") or []]
        )
    )
    found = []
    for document in documents:
        shared = news_topics.intersection(document.get("topics") or [])
        if not shared:
            continue
        paragraphs = [part.strip() for part in (document.get("text") or "").split("\n\n") if part.strip()]
        best_text = paragraphs[0] if paragraphs else (document.get("text") or "")
        best_score = -1
        for paragraph in paragraphs or [best_text]:
            score = len(tokens(paragraph) & query)
            if score > best_score:
                best_score = score
                best_text = paragraph
        found.append(
            {
                "id": document["id"],
                "title": document["title"],
                "origin": document.get("origin"),
                "is_bank_research": bool(document.get("is_bank_research")),
                "source_url": document.get("source_url"),
                "excerpt": best_text[:800],
                "overlap": len(shared),
            }
        )
    found.sort(key=lambda item: (not item["is_bank_research"], -item["overlap"], item["id"]))
    return found[:limit]


BANK_ABSENT = (
    "Подходящий материал аналитики Альфа-Банка не найден. "
    "Демонстрационные справки, если они показаны отдельно, не являются позицией банка и не подменяют ее."
)
