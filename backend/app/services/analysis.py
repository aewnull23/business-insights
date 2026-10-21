from app.services.impact import evaluate, level_of, score_of
from app.services.quality import check, repair, safe_fallback
from app.services.retrieval import BANK_ABSENT

BUCKETS = (
    ("attributes", "profile"),
    ("consequences", "ai"),
    ("risks", "ai"),
    ("opportunities", "ai"),
    ("actions", "action"),
)


def build_analysis(company: dict, news: dict, documents: list[dict]) -> dict:
    fired = evaluate(company, news)
    draft = _draft(company, news, documents, fired)
    issues = check(draft)
    fixes: list[str] = []
    revised = False
    if issues:
        draft = repair(draft, issues)
        fixes = list(draft.get("quality_fixes") or [])
        revised = True
        if check(draft):
            draft = safe_fallback(draft)
            fixes.append("Повторная проверка сняла оставшиеся слабые формулировки.")
    view = _present(company, news, draft, fired)
    view["quality"] = {"passed": True, "revised": revised, "fixes": fixes}
    return view


def origin_label(news: dict) -> str:
    origin = news.get("origin")
    if origin == "demonstration":
        return "Демонстрационный сюжет, не живая лента"
    if origin == "rss":
        return "Внешняя RSS-лента, текст не проверялся редакцией"
    return "Материал из подключенного источника"


def _draft(company: dict, news: dict, documents: list[dict], fired: list[dict]) -> dict:
    bank_docs = [item for item in documents if item.get("is_bank_research")]
    library = [item for item in documents if not item.get("is_bank_research")]
    draft = {
        "fired_rule_ids": [item["id"] for item in fired],
        "source_facts": [],
        "confirmed_facts": [],
        "attributes": [],
        "why": [],
        "consequences": [],
        "risks": [],
        "opportunities": [],
        "actions": [],
        "unknowns": [],
        "documents": library,
        "bank": {
            "found": bool(bank_docs),
            "message": "Найден материал, помеченный как аналитика банка." if bank_docs else BANK_ABSENT,
            "items": [
                {
                    "text": document["excerpt"],
                    "title": document["title"],
                    "kind": "bank",
                    "basis": [f"doc:{document['id']}"],
                }
                for document in bank_docs
            ],
        },
    }
    for fact in news.get("facts") or []:
        origin = "verified_feed" if fact.get("verification") == "confirmed" and news.get("origin") == "verified_feed" else news.get("origin")
        claim = {
            "text": fact["text"],
            "kind": "confirmed" if origin == "verified_feed" else "source",
            "basis": [f"fact:{fact['id']}", f"news:{news['id']}"],
            "origin": origin,
            "verification": fact.get("verification"),
        }
        if claim["kind"] == "confirmed":
            draft["confirmed_facts"].append(claim)
        else:
            draft["source_facts"].append(claim)
    if not fired:
        draft["unknowns"].append(
            "Правила не нашли признака, который связывает сюжет с заполненными полями профиля. Влияние из этого совпадения не выводится."
        )
    seen = set()
    for item in fired:
        basis = _basis(company, news, item["id"])
        effect = item["effect"]
        draft["why"].append({"text": effect["reason"], "kind": "ai", "basis": basis})
        for bucket, kind in BUCKETS:
            for text in effect[bucket]:
                draft[bucket].append({"text": text, "kind": kind, "basis": basis})
        for text in effect["unknowns"]:
            if text not in seen:
                draft["unknowns"].append(text)
                seen.add(text)
    return draft


def _present(company: dict, news: dict, draft: dict, fired: list[dict]) -> dict:
    sources = _sources(company, news, draft, fired)
    titles = {item["id"]: item["title"] for item in sources}

    def show(claims: list[dict]) -> list[dict]:
        shown = []
        for claim in claims:
            shown.append(
                {
                    "text": claim["text"],
                    "kind": claim["kind"],
                    "basis": claim.get("basis") or [],
                    "basis_labels": [titles.get(item, item) for item in claim.get("basis") or []],
                    "title": claim.get("title"),
                    "note": claim.get("note"),
                }
            )
        return shown

    document_items = []
    for document in draft["documents"]:
        note = (
            "Демонстрационная справка. Не является аналитикой Альфа-Банка."
            if document.get("origin") == "demonstration"
            else "Фрагмент из подключенной библиотеки."
        )
        document_items.append(
            {
                "text": document["excerpt"],
                "title": document["title"],
                "kind": "source",
                "basis": [f"doc:{document['id']}"],
                "basis_labels": [document["title"]],
                "note": note,
            }
        )
    bank_items = show(draft["bank"]["items"])
    score = score_of(fired)
    return {
        "company_id": company["id"],
        "news_id": news["id"],
        "title": news["title"],
        "published_at": news["published_at"],
        "category": news.get("category"),
        "origin": news.get("origin"),
        "origin_label": origin_label(news),
        "source_name": news.get("source_name"),
        "source_url": news.get("source_url"),
        "relevance": {
            "score": score,
            "level": level_of(score),
            "reasons": [
                {"rule_id": item["id"], "weight": round(item["weight"] / 100, 2), "text": item["effect"]["reason"]}
                for item in fired
            ],
        },
        "generation": {
            "mode": "rules",
            "model": None,
            "narrative": None,
            "note": "Модель не вызывалась. Выводы собраны правилами из профиля и сведений источника.",
        },
        "sections": [
            _section("happened", "Что произошло", show([
                {"text": news.get("summary") or news["title"], "kind": "source", "basis": [f"news:{news['id']}"]}
            ])),
            _section(
                "confirmed",
                "Подтвержденные факты",
                show(draft["confirmed_facts"]),
                "Подтвержденных внешней проверкой фактов нет. Сведения демонстрационного сюжета и неразобранной ленты сюда не попадают.",
            ),
            _section("source_facts", "Сведения из материала", show(draft["source_facts"])),
            _section(
                "why",
                "Почему это важно для компании",
                show(draft["why"]),
                "Значимых совпадений с заполненными полями профиля нет.",
                "Совпадения объясняют отбор сюжета. Это не доказанное влияние на финансовый результат.",
            ),
            _section("attributes", "Какие данные профиля повлияли", show(draft["attributes"])),
            _section("consequences", "Потенциальные последствия", show(draft["consequences"])),
            _section("risks", "Риски", show(draft["risks"])),
            _section("opportunities", "Возможности", show(draft["opportunities"]), "Явной возможности, которая следует из профиля и сюжета, нет."),
            _section("actions", "Что можно проверить", show(draft["actions"])),
            _section("bank", "Аналитика Альфа-Банка", bank_items, draft["bank"]["message"] if not draft["bank"]["found"] else None),
            _section("documents", "Найденные аналитические материалы", document_items, "В библиотеке нет фрагмента по теме этого сюжета."),
            _section("unknowns", "Что остается неизвестным", [
                {"text": text, "kind": "unknown", "basis": [], "basis_labels": [], "title": None, "note": None}
                for text in draft["unknowns"]
            ]),
        ],
        "sources": sources,
        "bank_found": draft["bank"]["found"],
    }


def _section(section_id: str, title: str, items: list[dict], empty: str | None = None, lead: str | None = None) -> dict:
    return {"id": section_id, "title": title, "lead": lead, "empty": empty, "items": items}


def _basis(company: dict, news: dict, rule_id: str) -> list[str]:
    values = [f"profile:{company['id']}", f"news:{news['id']}", f"rule:{rule_id}"]
    values.extend(f"fact:{fact['id']}" for fact in news.get("facts") or [])
    return values


def _sources(company: dict, news: dict, draft: dict, fired: list[dict]) -> list[dict]:
    kind = "demonstration_news" if news.get("origin") == "demonstration" else "external_news"
    rows = [
        {
            "id": f"news:{news['id']}",
            "title": news["title"],
            "kind": kind,
            "url": news.get("source_url"),
            "note": origin_label(news),
        },
        {
            "id": f"profile:{company['id']}",
            "title": "Профиль компании",
            "kind": "company_profile",
            "url": None,
            "note": "Только поля, которые есть в загруженном профиле.",
        },
    ]
    for fact in news.get("facts") or []:
        rows.append(
            {
                "id": f"fact:{fact['id']}",
                "title": fact["text"],
                "kind": "source_statement",
                "url": news.get("source_url"),
                "note": "Сведение из текста материала, не отдельная внешняя проверка."
                if fact.get("verification") != "confirmed"
                else "Сведение помечено как подтвержденное.",
            }
        )
    for item in fired:
        rows.append(
            {
                "id": f"rule:{item['id']}",
                "title": item["title"],
                "kind": "engine_rule",
                "url": None,
                "note": "Правило сопоставления движка. Это не внешний документ.",
            }
        )
    for document in list(draft["documents"]) + [
        {"id": item["basis"][0].split(":", 1)[1], "title": item.get("title"), "source_url": None, "is_bank_research": True}
        for item in draft["bank"]["items"]
        if item.get("basis")
    ]:
        rows.append(
            {
                "id": f"doc:{document['id']}",
                "title": document.get("title") or document["id"],
                "kind": "bank_document" if document.get("is_bank_research") else "demonstration_document",
                "url": document.get("source_url"),
                "note": "Материал библиотеки.",
            }
        )
    return rows
