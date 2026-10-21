from app.config import LARGE_BUSINESS_REVENUE
from app.datasets import company_by_id, excluded_preview, load_companies
from app.textutil import format_int, format_money, format_pct

CORE_GAP_FIELDS = (
    ("industry", "отрасль"),
    ("revenue_rub", "выручка"),
    ("employees", "численность"),
    ("region", "регион"),
    ("bank_products", "банковские продукты"),
    ("payments", "платежи"),
    ("counterparties", "контрагенты"),
)


def _missing(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def core_gaps(company: dict) -> list[str]:
    return [label for key, label in CORE_GAP_FIELDS if _missing(company.get(key))]


def get_company(company_id: str) -> dict | None:
    return company_by_id(company_id)


def workspace_companies() -> list[dict]:
    result = []
    for company in load_companies():
        if company.get("large_business") or company.get("include_incomplete"):
            result.append(_public(company))
    return result


def excluded_companies() -> list[dict]:
    return list(excluded_preview())


def _public(company: dict) -> dict:
    return {
        "id": company["id"],
        "synthetic_u": company.get("synthetic_u"),
        "name": company["name"],
        "industry": company.get("industry"),
        "city": company.get("city"),
        "business_size": company.get("business_size"),
        "large_business": bool(company.get("large_business")),
        "include_incomplete": bool(company.get("include_incomplete")),
        "client_type": company.get("client_type"),
        "demo": company.get("demo", True),
        "revenue_threshold": LARGE_BUSINESS_REVENUE,
    }


def list_public() -> list[dict]:
    return workspace_companies()


def _products(company: dict) -> str | None:
    products = company.get("bank_products")
    if _missing(products):
        return None
    return ", ".join(products)


def _group(company: dict) -> str | None:
    group = company.get("group")
    if _missing(group):
        return None
    role = group.get("role")
    name = group.get("name") or "группа без названия"
    mates = group.get("mates") or []
    text = f"{name}, {role}" if role else name
    if mates:
        text += "; также в группе: " + ", ".join(item.get("name") or item.get("synthetic_u") for item in mates)
    return text


def _counterparties(company: dict) -> str | None:
    rows = company.get("counterparties")
    if _missing(rows):
        return None
    parts = []
    for row in rows:
        bit = row.get("name") or "контрагент"
        if row.get("role"):
            bit += f" · {row['role']}"
        if row.get("share_of_revenue") is not None:
            bit += f" · {format_pct(row['share_of_revenue'])} выручки"
        if row.get("share_of_costs") is not None:
            bit += f" · {format_pct(row['share_of_costs'])} затрат"
        parts.append(bit)
    return "; ".join(parts)


def _payments(company: dict) -> str | None:
    payments = company.get("payments")
    if _missing(payments):
        return None
    parts = []
    shares = payments.get("currency_share") or {}
    if shares:
        parts.append(" · ".join(f"{code} {format_pct(share)}" for code, share in shares.items()))
    export_share = payments.get("export_share_of_revenue")
    if export_share is not None:
        parts.append(f"экспорт {format_pct(export_share)} выручки")
    dependence = payments.get("import_dependence")
    if dependence:
        parts.append(f"зависимость от импорта: {dependence}")
    return " · ".join(parts) if parts else None


def _okved(company: dict) -> str | None:
    code = company.get("okved")
    if _missing(code):
        return None
    name = company.get("okved_name")
    return f"{code} — {name}" if name else code


def _owner(company: dict) -> str | None:
    mark = company.get("has_key_owner_mark")
    persons = company.get("related_persons") or []
    if mark is None and not persons:
        return None
    bits = []
    if mark is True:
        bits.append("есть признак ключевого собственника")
    elif mark is False:
        bits.append("признак ключевого собственника не установлен")
    if persons:
        bits.append("связанных физлиц: " + ", ".join(item["synthetic_f"] for item in persons))
    links = company.get("shared_person_links") or []
    if links:
        bits.append(
            "общие физлица с: "
            + ", ".join(f"{item.get('name')} ({item['synthetic_f']})" for item in links)
        )
    bits.append("ФИО и доли не раскрываются: данные обезличены")
    return "; ".join(bits)


def profile_view(company: dict) -> dict:
    rows = [
        ("Идентификатор датасета", company.get("synthetic_u")),
        ("Отрасль", company.get("industry")),
        ("ОКВЭД", _okved(company)),
        ("Тип организации", company.get("org_type")),
        ("Форма собственности", company.get("ownership")),
        ("Тип клиента", company.get("client_type")),
        ("Размер бизнеса", company.get("business_size")),
        ("Выручка", format_money(company.get("revenue_rub"))),
        ("Регион", company.get("region")),
        ("Город", company.get("city")),
        ("Стадия", company.get("stage")),
        ("Возраст компании", company.get("company_age")),
        ("Сотрудники", format_int(company.get("employees"))),
        ("Численность ФНС", company.get("workers_fns")),
        ("Численность СПАРК", company.get("workers_spark")),
        ("Банковские продукты", _products(company)),
        ("Внешняя торговля", company.get("fts_country") if company.get("fts_flag") else ("нет отметки ФТС" if company.get("fts_flag") is False else None)),
        ("Группа компаний", _group(company)),
        ("Связанные лица", _owner(company)),
        ("Контрагенты", _counterparties(company)),
        ("Платежи", _payments(company)),
    ]
    return {
        "id": company["id"],
        "synthetic_u": company.get("synthetic_u"),
        "name": company["name"],
        "demo": company.get("demo", True),
        "disclaimer": company.get("disclaimer") or "",
        "large_business": bool(company.get("large_business")),
        "core_gaps": core_gaps(company),
        "rows": [{"label": label, "value": value} for label, value in rows],
        "profile": company,
    }
