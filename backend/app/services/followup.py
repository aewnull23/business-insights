from app.providers.llm import llm_status
from app.services.quality import narrative_is_grounded
from app.textutil import format_money, format_int, normalize, tokens

CREDIT = ("кредитная линия", "овердрафт", "кредит")


def answer_question(company: dict, news: dict, analysis: dict, question: str) -> dict:
    query = normalize(question)
    if "альфа" in query:
        return _bank(analysis)
    if any(word in query for word in ("бенефициар", "владел", "акционер", "собственник")):
        return _make(
            "В профиле нет сведений о бенефициарах, владельцах и акционерах. Восстанавливать их из обезличенных данных нельзя.",
            "unknown",
            [f"profile:{company['id']}"],
            ["Профиль компании"],
        )
    if any(word in query for word in ("точно", "гарант", "обязательн", "обруш")):
        unknowns = _section(analysis, "unknowns")["items"]
        extra = " " + unknowns[0]["text"] if unknowns else ""
        return _make(
            "Утверждать гарантированное последствие нельзя. Разбор отделяет сведения источника от гипотез." + extra,
            "unknown",
            [f"news:{news['id']}", f"profile:{company['id']}"],
            [news["title"], "Профиль компании"],
        )
    if "факт" in query:
        return _facts(analysis, news)
    if "выруч" in query:
        return _field(
            company,
            format_money(company.get("revenue_rub")),
            "В профиле выручка {value}. Это поле анкеты, а не вывод из новости.",
            "Выручка в профиле не указана. Подставлять ее нельзя.",
        )
    if any(word in query for word in ("сотруд", "числен", "персонал")):
        return _field(
            company,
            format_int(company.get("employees")),
            "В профиле численность — {value}. Разбивки по ролям нет.",
            "Численность в профиле не указана и не используется в оценке.",
        )
    if "оквэд" in query or "оквед" in query:
        code = company.get("okved")
        if company.get("okved_name"):
            code = f"{code} — {company['okved_name']}"
        return _field(company, code, "ОКВЭД в профиле: {value}.", "ОКВЭД в профиле не указан.")
    if "регион" in query or "город" in query:
        place = ", ".join(part for part in (company.get("city"), company.get("region")) if part)
        return _field(company, place or None, "В профиле указано: {value}.", "Регион и город в профиле не указаны.")
    if "контрагент" in query:
        rows = company.get("counterparties") or []
        if not rows:
            return _make(
                "Контрагенты в профиле не указаны. Называть покупателей или поставщиков нельзя.",
                "unknown",
                [f"profile:{company['id']}"],
                ["Профиль компании"],
            )
        text = "; ".join(_counterparty_line(row) for row in rows)
        return _make(
            "В профиле указаны контрагенты: " + text + ". Это не прогноз их поведения.",
            "profile",
            [f"profile:{company['id']}"],
            ["Профиль компании"],
        )
    if any(word in query for word in ("кредит", "овердрафт", "эквайринг", "лизинг", "депозит", "продукт")):
        return _products(company, analysis, query)
    if "неизв" in query or "не хватает" in query:
        items = _section(analysis, "unknowns")["items"]
        if not items:
            return _make(
                "Отдельный список неизвестного для этого разбора пуст.",
                "unknown",
                [f"news:{news['id']}"],
                [news["title"]],
            )
        return _make(" ".join(item["text"] for item in items), "unknown", [], [])
    matched = _overlap(analysis, query)
    if matched:
        kind = matched["kind"] if matched["kind"] in {"ai", "source", "profile", "bank", "unknown", "action"} else "ai"
        return _make(matched["text"], kind, matched.get("basis") or [], matched.get("basis_labels") or [])
    return _make(
        "В профиле компании и в разборе этого события нет данных для ответа. Недостающее нельзя заменять предположением.",
        "unknown",
        [f"profile:{company['id']}", f"news:{news['id']}"],
        ["Профиль компании", news["title"]],
    )


def _bank(analysis: dict) -> dict:
    section = _section(analysis, "bank")
    if analysis.get("bank_found") and section["items"]:
        text = " ".join(item["text"] for item in section["items"])
        return _make(text, "bank", section["items"][0].get("basis") or [], section["items"][0].get("basis_labels") or [])
    return _make(
        section.get("empty")
        or "Подходящий материал аналитики Альфа-Банка не найден. Демонстрационные справки не заменяют позицию банка.",
        "bank",
        [],
        [],
    )


def _facts(analysis: dict, news: dict) -> dict:
    confirmed = _section(analysis, "confirmed")["items"]
    source = _section(analysis, "source_facts")["items"]
    if confirmed:
        body = "Подтвержденные факты: " + " ".join(item["text"] for item in confirmed)
        kind = "confirmed"
    else:
        body = "Подтвержденных внешней проверкой фактов нет."
        kind = "source"
    if source:
        body += " В материале есть такие сведения: " + " ".join(item["text"] for item in source)
    return _make(body, kind, [f"news:{news['id']}"], [news["title"]])


def _products(company: dict, analysis: dict, query: str) -> dict:
    have = company.get("bank_products") or []
    if not have:
        return _make(
            "Банковские продукты в профиле не указаны. Считать, что кредитная линия или другой продукт подключены, нельзя.",
            "unknown",
            [f"profile:{company['id']}"],
            ["Профиль компании"],
        )
    if "кредит" in query or "овердрафт" in query:
        credit = [item for item in have if item in CREDIT]
        if not credit:
            return _make(
                "В профиле нет кредитной линии, овердрафта или кредита. Правило стоимости долга на эту компанию не опирается.",
                "profile",
                [f"profile:{company['id']}"],
                ["Профиль компании"],
            )
        related = _related(analysis, ("кредит", "ставк", "долг"))
        text = f"В профиле есть: {', '.join(credit)}. " + " ".join(item["text"] for item in related[:3])
        return _make(text, "ai", [f"profile:{company['id']}"], ["Профиль компании"])
    return _make(
        "В профиле указаны продукты: " + ", ".join(have) + ". Наличие продукта не равно эффекту новости.",
        "profile",
        [f"profile:{company['id']}"],
        ["Профиль компании"],
    )


def _field(company: dict, value: str | None, template: str, missing: str) -> dict:
    if not value:
        return _make(missing, "unknown", [f"profile:{company['id']}"], ["Профиль компании"])
    return _make(template.format(value=value), "profile", [f"profile:{company['id']}"], ["Профиль компании"])


def _related(analysis: dict, stems: tuple[str, ...]) -> list[dict]:
    found = []
    for section in analysis["sections"]:
        if section["id"] not in {"why", "consequences", "risks", "actions", "unknowns", "attributes"}:
            continue
        for item in section["items"]:
            lowered = item["text"].lower()
            if any(stem in lowered for stem in stems):
                found.append(item)
    return found


def _overlap(analysis: dict, query: str) -> dict | None:
    wanted = tokens(query)
    best = None
    best_score = 0.0
    for section in analysis["sections"]:
        for item in section["items"]:
            have = tokens(item["text"])
            if not wanted or not have:
                continue
            score = len(wanted & have) / len(wanted)
            if score > best_score:
                best_score = score
                best = item
    if best is not None and best_score >= 0.34:
        return best
    return None


def _counterparty_line(row: dict) -> str:
    bits = [row.get("name") or "контрагент"]
    if row.get("role"):
        bits.append(row["role"])
    return " — ".join(bits)


def _section(analysis: dict, section_id: str) -> dict:
    for section in analysis["sections"]:
        if section["id"] == section_id:
            return section
    return {"items": [], "empty": None}


def _make(answer: str, kind: str, basis: list[str], labels: list[str]) -> dict:
    status = llm_status()
    generation = {"mode": "rules", "model": None}
    if status["mode"] == "live":
        from app.providers.llm import complete

        packet = answer
        text = complete(
            [
                {
                    "role": "system",
                    "content": "Сожми ответ до двух предложений. Не добавляй фактов и чисел, которых нет в тексте пользователя.",
                },
                {"role": "user", "content": packet},
            ]
        )
        if text and narrative_is_grounded(text, packet, False):
            answer = text.strip()
            generation = {"mode": "llm", "model": status["model"]}
    return {"answer": answer, "kind": kind, "basis": basis, "basis_labels": labels, "generation": generation}
