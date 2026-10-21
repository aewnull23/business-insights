from app.datasets import load_companies
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
    for company in load_companies():
        if company["id"] == company_id:
            return company
    return None


def list_public() -> list[dict]:
    result = []
    for company in load_companies():
        result.append(
            {
                "id": company["id"],
                "name": company["name"],
                "industry": company.get("industry"),
                "city": company.get("city"),
                "business_size": company.get("business_size"),
                "demo": company.get("demo", True),
            }
        )
    return result


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
    return f"{name}, {role}" if role else name


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


def profile_view(company: dict) -> dict:
    rows = [
        ("Отрасль", company.get("industry")),
        ("ОКВЭД", _okved(company)),
        ("Размер бизнеса", company.get("business_size")),
        ("Выручка", format_money(company.get("revenue_rub"))),
        ("Регион", company.get("region")),
        ("Город", company.get("city")),
        ("Стадия", company.get("stage")),
        ("Сотрудники", format_int(company.get("employees"))),
        ("Банковские продукты", _products(company)),
        ("Группа компаний", _group(company)),
        ("Контрагенты", _counterparties(company)),
        ("Платежи", _payments(company)),
    ]
    return {
        "id": company["id"],
        "name": company["name"],
        "demo": company.get("demo", True),
        "disclaimer": company.get("disclaimer") or "",
        "core_gaps": core_gaps(company),
        "rows": [{"label": label, "value": value} for label, value in rows],
        "profile": company,
    }
