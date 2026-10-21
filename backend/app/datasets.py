import csv
import json
from functools import lru_cache

from app.config import DATA_DIR, LARGE_BUSINESS_REVENUE
from app.schemas import Company, Document, NewsItem, UserAccount

UID_COLUMNS = (
    "SYNTHETIC_U",
    "ORG_TYPE",
    "OKFS_NAME",
    "COMPANY_AGE_YEARS_GRADATION",
    "ECO_MARK_LABEL",
    "MAINOKVED_CODE",
    "MAINOKVED_NAME",
    "NEGATIVEMARK",
    "AMOUNT_WORKERS_FNS_GRADATION",
    "AMOUNT_WORKERS_SPARK_GRADATION",
    "CL_TYPE",
    "CL_PRODUCT_RKO_MARK",
    "CL_PRODUCT_GAR_MARK",
    "CL_PRODUCT_LOA_MARK",
    "CL_PRODUCT_LEA_MARK",
    "CL_PRODUCT_DEP_MARK",
    "CL_PRODUCT_ZPP_MARK",
    "FTS_FLAG",
    "FTS_COUNTRY_NAME",
    "FACTORING_MARK",
    "REVENUE_COMPANY",
    "GROUP_ID",
    "CITY",
    "REGION",
)
FID_COLUMNS = ("SYNTHETIC_F", "CITY_NAME", "RC_NAME", "SYNTHETIC_U")
PAY_COLUMNS = ("BENEFICIARY", "PAYER", "PAY_AMT", "PAY_CNT")
PRODUCT_FLAGS = (
    ("CL_PRODUCT_RKO_MARK", "расчетный счет"),
    ("CL_PRODUCT_GAR_MARK", "гарантии"),
    ("CL_PRODUCT_LOA_MARK", "кредитная линия"),
    ("CL_PRODUCT_LEA_MARK", "лизинг"),
    ("CL_PRODUCT_DEP_MARK", "депозит"),
    ("CL_PRODUCT_ZPP_MARK", "зарплатный проект"),
    ("FACTORING_MARK", "факторинг"),
)


def _read_json(name: str):
    path = DATA_DIR / name
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _read_csv(name: str, required: tuple[str, ...]) -> list[dict[str, str]]:
    path = DATA_DIR / name
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in required if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{name}: нет колонок {missing}")
        return [{key: (row.get(key) or "").strip() for key in required} for row in reader]


def _unique(ids: list[str], label: str) -> None:
    if len(ids) != len(set(ids)):
        raise ValueError(f"Повторяющиеся идентификаторы в {label}")


def _flag(value: str) -> bool | None:
    if value == "":
        return None
    return value in {"1", "true", "True", "да"}


def _number(value: str) -> int | None:
    if value == "":
        return None
    cleaned = value.replace(" ", "").replace(",", ".")
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def _workers(value: str) -> int | None:
    if not value:
        return None
    digits = "".join(ch if ch.isdigit() else " " for ch in value).split()
    if not digits:
        return None
    return int(digits[0])


def _products(row: dict[str, str], extra: list[str] | None) -> list[str] | None:
    names = []
    known = False
    for column, label in PRODUCT_FLAGS:
        flag = _flag(row.get(column, ""))
        if flag is not None:
            known = True
        if flag:
            names.append(label)
    for item in extra or []:
        if item not in names:
            names.append(item)
    if not known and not extra:
        return None
    return names


def _persons(uid: str, links: list[dict[str, str]]) -> list[dict]:
    found = []
    for row in links:
        if row["SYNTHETIC_U"] != uid:
            continue
        found.append(
            {
                "synthetic_f": row["SYNTHETIC_F"],
                "city": row["CITY_NAME"] or None,
                "region": row["RC_NAME"] or None,
            }
        )
    return found


def _group_mates(uid: str, group_id: str, rows: list[dict[str, str]], labels: dict) -> list[dict]:
    if not group_id:
        return []
    mates = []
    for row in rows:
        if row["GROUP_ID"] != group_id or row["SYNTHETIC_U"] == uid:
            continue
        label = labels.get(row["SYNTHETIC_U"]) or {}
        mates.append(
            {
                "synthetic_u": row["SYNTHETIC_U"],
                "id": label.get("id") or row["SYNTHETIC_U"].lower(),
                "name": label.get("name") or row["SYNTHETIC_U"],
            }
        )
    return mates


def _shared_persons(uid: str, links: list[dict[str, str]], labels: dict) -> list[dict]:
    own = {row["SYNTHETIC_F"] for row in links if row["SYNTHETIC_U"] == uid}
    if not own:
        return []
    shared = []
    seen = set()
    for row in links:
        if row["SYNTHETIC_U"] == uid or row["SYNTHETIC_F"] not in own:
            continue
        key = (row["SYNTHETIC_F"], row["SYNTHETIC_U"])
        if key in seen:
            continue
        seen.add(key)
        label = labels.get(row["SYNTHETIC_U"]) or {}
        shared.append(
            {
                "synthetic_f": row["SYNTHETIC_F"],
                "synthetic_u": row["SYNTHETIC_U"],
                "name": label.get("name") or row["SYNTHETIC_U"],
            }
        )
    return shared


def _counterparties(uid: str, payments: list[dict[str, str]], revenue: int | None, labels: dict) -> list[dict] | None:
    rows = []
    for item in payments:
        if item["BENEFICIARY"] == uid:
            other = item["PAYER"]
            role = "покупатель"
            amount = _number(item["PAY_AMT"])
            share_key = "share_of_revenue"
        elif item["PAYER"] == uid:
            other = item["BENEFICIARY"]
            role = "поставщик"
            amount = _number(item["PAY_AMT"])
            share_key = "share_of_costs"
        else:
            continue
        names = (labels.get(uid) or {}).get("counterparty_names") or {}
        other_label = labels.get(other) or {}
        row = {
            "synthetic_u": other,
            "name": names.get(other) or other_label.get("name") or other,
            "role": role,
            "pay_amt": amount,
            "pay_cnt": _number(item["PAY_CNT"]),
        }
        if amount is not None and revenue:
            row[share_key] = round(amount / revenue, 4)
        rows.append(row)
    return rows or None


def _company(row: dict[str, str], labels: dict, links: list[dict[str, str]], payments: list[dict[str, str]], uid_rows: list[dict[str, str]]) -> dict:
    uid = row["SYNTHETIC_U"]
    label = labels.get(uid) or {}
    revenue = _number(row["REVENUE_COMPANY"])
    products = _products(row, label.get("extra_products"))
    group_id = row["GROUP_ID"] or None
    mates = _group_mates(uid, group_id or "", uid_rows, labels)
    payload = {
        "id": label.get("id") or uid.lower(),
        "synthetic_u": uid,
        "name": label.get("name") or uid,
        "demo": True,
        "disclaimer": label.get("disclaimer")
        or "Обезличенный синтетический профиль по схеме датасета кейса. Не является реальным юридическим лицом.",
        "industry": label.get("industry"),
        "okved": row["MAINOKVED_CODE"] or None,
        "okved_name": row["MAINOKVED_NAME"] or None,
        "revenue_rub": revenue,
        "business_size": "крупный" if revenue is not None and revenue > LARGE_BUSINESS_REVENUE else ("ниже порога кейса" if revenue is not None else None),
        "large_business": bool(revenue is not None and revenue > LARGE_BUSINESS_REVENUE),
        "include_incomplete": bool(label.get("include_incomplete")),
        "region": row["REGION"] or None,
        "city": row["CITY"] or None,
        "stage": row["ECO_MARK_LABEL"] or None,
        "company_age": row["COMPANY_AGE_YEARS_GRADATION"] or None,
        "org_type": row["ORG_TYPE"] or None,
        "ownership": row["OKFS_NAME"] or None,
        "client_type": row["CL_TYPE"] or None,
        "employees": _workers(row["AMOUNT_WORKERS_SPARK_GRADATION"]) or _workers(row["AMOUNT_WORKERS_FNS_GRADATION"]),
        "workers_fns": row["AMOUNT_WORKERS_FNS_GRADATION"] or None,
        "workers_spark": row["AMOUNT_WORKERS_SPARK_GRADATION"] or None,
        "bank_products": products,
        "has_key_owner_mark": _flag(row["NEGATIVEMARK"]),
        "fts_flag": _flag(row["FTS_FLAG"]),
        "fts_country": row["FTS_COUNTRY_NAME"] or None,
        "group": {"id": group_id, "name": "Группа «Северный контур»", "role": "производственная компания", "mates": mates} if group_id else None,
        "related_persons": _persons(uid, links),
        "shared_person_links": _shared_persons(uid, links, labels),
        "counterparties": _counterparties(uid, payments, revenue, labels),
        "payments": label.get("payments_overlay") or None,
        "source": "df_Uid_data_hack.csv",
    }
    return Company.model_validate(payload).model_dump()


@lru_cache(maxsize=1)
def load_labels() -> dict:
    data = _read_json("company_labels.json")
    if not isinstance(data, dict):
        raise ValueError("company_labels.json должен быть объектом")
    return data


@lru_cache(maxsize=1)
def load_uid_rows() -> tuple[dict, ...]:
    return tuple(_read_csv("df_Uid_data_hack.csv", UID_COLUMNS))


@lru_cache(maxsize=1)
def load_fid_rows() -> tuple[dict, ...]:
    return tuple(_read_csv("df_Fid_Uid_link_hack.csv", FID_COLUMNS))


@lru_cache(maxsize=1)
def load_pay_rows() -> tuple[dict, ...]:
    return tuple(_read_csv("df_Pay_data_hack.csv", PAY_COLUMNS))


@lru_cache(maxsize=1)
def load_companies() -> tuple[dict, ...]:
    labels = load_labels()
    uids = list(load_uid_rows())
    links = list(load_fid_rows())
    payments = list(load_pay_rows())
    rows = [_company(row, labels, links, payments, uids) for row in uids]
    _unique([row["id"] for row in rows], "компаниях")
    return tuple(rows)


@lru_cache(maxsize=1)
def load_users() -> tuple[dict, ...]:
    rows = [UserAccount.model_validate(item).model_dump() for item in _read_json("users.json")]
    _unique([row["id"] for row in rows], "пользователях")
    company_ids = {item["id"] for item in load_companies()}
    for row in rows:
        if row["company_id"] not in company_ids:
            raise ValueError(f"Пользователь {row['id']} ссылается на неизвестную компанию")
    return tuple(rows)


@lru_cache(maxsize=1)
def load_news_seed() -> tuple[dict, ...]:
    rows = [NewsItem.model_validate(item).model_dump() for item in _read_json("news.json")]
    _unique([row["id"] for row in rows], "новостях")
    return tuple(rows)


@lru_cache(maxsize=1)
def load_documents() -> tuple[dict, ...]:
    rows = [Document.model_validate(item).model_dump() for item in _read_json("documents.json")]
    _unique([row["id"] for row in rows], "документах")
    return tuple(rows)


def clear_caches() -> None:
    load_labels.cache_clear()
    load_uid_rows.cache_clear()
    load_fid_rows.cache_clear()
    load_pay_rows.cache_clear()
    load_companies.cache_clear()
    load_users.cache_clear()
    load_news_seed.cache_clear()
    load_documents.cache_clear()
