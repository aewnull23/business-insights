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


def _csv_path(*names: str):
    for name in names:
        path = DATA_DIR / name
        if path.exists():
            return path
    raise FileNotFoundError(", ".join(names))


def _read_csv(path, required: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
        reader = csv.DictReader(handle, delimiter=delimiter)
        missing = [column for column in required if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path.name}: нет колонок {missing}")
        return [{key: (row.get(key) or "").strip() for key in required} for row in reader]


def industry_of(row: dict[str, str], label: dict | None = None) -> str | None:
    custom = (label or {}).get("industry")
    if custom:
        return custom
    code = (row.get("MAINOKVED_CODE") or "").strip()
    prefix = code.split(".")[0][:2] if code else ""
    name = row.get("MAINOKVED_NAME") or ""
    low = name.lower().replace("ё", "е")
    if prefix in {"24", "25"} or "сталь" in low:
        return "Металлургия"
    if "металл" in low:
        return "Торговля металлами"
    if prefix == "47":
        return "Розничная торговля"
    if prefix in {"49", "50", "51", "52"}:
        return "Транспорт и логистика"
    if prefix in {"62", "63"}:
        return "Информационные технологии"
    if prefix in {"01", "02"}:
        return "Сельское хозяйство"
    return name or None


def _unique(ids: list[str], label: str) -> None:
    if len(ids) != len(set(ids)):
        raise ValueError(f"Повторяющиеся идентификаторы в {label}")


def _flag(value: str) -> bool | None:
    if value == "":
        return None
    cleaned = value.replace(",", ".").strip()
    try:
        return float(cleaned) != 0
    except ValueError:
        return cleaned.lower() in {"true", "да", "yes"}


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


def _persons(uid: str) -> list[dict]:
    found = []
    for row in load_links_by_uid().get(uid, ()):
        found.append(
            {
                "synthetic_f": row["SYNTHETIC_F"],
                "city": row["CITY_NAME"] or None,
                "region": row["RC_NAME"] or None,
            }
        )
        if len(found) >= 12:
            break
    return found


def _group_mates(uid: str, group_id: str, labels: dict) -> list[dict]:
    if not group_id:
        return []
    mates = []
    for other in load_group_index().get(group_id, ()):
        if other == uid:
            continue
        label = labels.get(other) or {}
        mates.append(
            {
                "synthetic_u": other,
                "id": label.get("id") or other.lower(),
                "name": label.get("name") or other,
            }
        )
        if len(mates) >= 5:
            break
    return mates


def _shared_persons(uid: str, labels: dict) -> list[dict]:
    own = [row["SYNTHETIC_F"] for row in load_links_by_uid().get(uid, ())]
    if not own:
        return []
    shared = []
    seen = set()
    by_person = load_links_by_person()
    for person in own:
        for row in by_person.get(person, ()):
            if row["SYNTHETIC_U"] == uid:
                continue
            key = (row["SYNTHETIC_F"], row["SYNTHETIC_U"])
            if key in seen:
                continue
            seen.add(key)
            other = row["SYNTHETIC_U"]
            label = labels.get(other) or {}
            shared.append(
                {
                    "synthetic_f": row["SYNTHETIC_F"],
                    "synthetic_u": other,
                    "name": label.get("name") or other,
                }
            )
            if len(shared) >= 8:
                return shared
    return shared


def _counterparties(uid: str, revenue: int | None, labels: dict) -> list[dict] | None:
    rows = []
    for item in load_pay_index().get(uid, ()):
        if item["BENEFICIARY"] == uid:
            other = item["PAYER"]
            role = "покупатель"
            share_key = "share_of_revenue"
        elif item["PAYER"] == uid:
            other = item["BENEFICIARY"]
            role = "поставщик"
            share_key = "share_of_costs"
        else:
            continue
        amount = _number(item["PAY_AMT"])
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
    rows.sort(key=lambda item: item.get("pay_amt") or 0, reverse=True)
    return rows[:8] or None


def _company(row: dict[str, str], labels: dict) -> dict:
    uid = row["SYNTHETIC_U"]
    label = labels.get(uid) or {}
    revenue = _number(row["REVENUE_COMPANY"])
    products = _products(row, label.get("extra_products"))
    group_id = row["GROUP_ID"] or None
    mates = _group_mates(uid, group_id or "", labels)
    payload = {
        "id": label.get("id") or uid.lower(),
        "synthetic_u": uid,
        "name": label.get("name") or uid,
        "demo": True,
        "disclaimer": label.get("disclaimer")
        or "Обезличенный профиль из оригинальной выгрузки организаторов. Название компании не раскрывается: в данных только идентификатор SYNTHETIC_U.",
        "industry": industry_of(row, label),
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
        "group": {"id": group_id, "name": label.get("group_name") or f"Группа {group_id}", "role": label.get("group_role"), "mates": mates} if group_id else None,
        "related_persons": _persons(uid),
        "shared_person_links": _shared_persons(uid, labels),
        "counterparties": _counterparties(uid, revenue, labels),
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
    return tuple(_read_csv(_csv_path("df_Uid_data_hack.csv"), UID_COLUMNS))


@lru_cache(maxsize=1)
def load_fid_rows() -> tuple[dict, ...]:
    return tuple(_read_csv(_csv_path("df_Fid_Uid_link_hack.csv"), FID_COLUMNS))


@lru_cache(maxsize=1)
def load_pay_rows() -> tuple[dict, ...]:
    return tuple(_read_csv(_csv_path("df_Uid_payment_hack.csv", "df_Pay_data_hack.csv"), PAY_COLUMNS))


@lru_cache(maxsize=1)
def load_links_by_uid() -> dict:
    index: dict[str, list] = {}
    for row in load_fid_rows():
        index.setdefault(row["SYNTHETIC_U"], []).append(row)
    return index


@lru_cache(maxsize=1)
def load_links_by_person() -> dict:
    index: dict[str, list] = {}
    for row in load_fid_rows():
        index.setdefault(row["SYNTHETIC_F"], []).append(row)
    return index


@lru_cache(maxsize=1)
def load_group_index() -> dict:
    index: dict[str, list] = {}
    for row in load_uid_rows():
        group_id = row["GROUP_ID"]
        if group_id:
            index.setdefault(group_id, []).append(row["SYNTHETIC_U"])
    return index


@lru_cache(maxsize=1)
def load_pay_index() -> dict:
    index: dict[str, list] = {}
    for row in load_pay_rows():
        index.setdefault(row["BENEFICIARY"], []).append(row)
        if row["PAYER"] != row["BENEFICIARY"]:
            index.setdefault(row["PAYER"], []).append(row)
    return index


@lru_cache(maxsize=1)
def load_uid_index() -> dict:
    labels = load_labels()
    index = {}
    for row in load_uid_rows():
        uid = row["SYNTHETIC_U"]
        index[uid] = row
        index[uid.lower()] = row
        custom = (labels.get(uid) or {}).get("id")
        if custom:
            index[custom] = row
    return index


def _is_workspace(row: dict[str, str], label: dict) -> bool:
    if label.get("include_incomplete"):
        return True
    revenue = _number(row["REVENUE_COMPANY"])
    return revenue is not None and revenue > LARGE_BUSINESS_REVENUE


@lru_cache(maxsize=1)
def load_companies() -> tuple[dict, ...]:
    labels = load_labels()
    rows = [_company(row, labels) for row in load_uid_rows() if _is_workspace(row, labels.get(row["SYNTHETIC_U"]) or {})]
    _unique([row["id"] for row in rows], "компаниях")
    return tuple(rows)


@lru_cache(maxsize=256)
def company_by_id(company_id: str) -> dict | None:
    row = load_uid_index().get(company_id)
    if not row:
        return None
    uid = row["SYNTHETIC_U"]
    for company in load_companies():
        if company.get("synthetic_u") == uid:
            return company
    return _company(row, load_labels())


@lru_cache(maxsize=1)
def excluded_preview(limit: int = 12) -> tuple[dict, ...]:
    labels = load_labels()
    rows = []
    for row in load_uid_rows():
        label = labels.get(row["SYNTHETIC_U"]) or {}
        if _is_workspace(row, label):
            continue
        revenue = _number(row["REVENUE_COMPANY"])
        if revenue is None:
            continue
        uid = row["SYNTHETIC_U"]
        rows.append(
            {
                "id": label.get("id") or uid.lower(),
                "synthetic_u": uid,
                "name": label.get("name") or uid,
                "industry": industry_of(row, label),
                "city": row["CITY"] or None,
                "business_size": "ниже порога кейса",
                "large_business": False,
                "include_incomplete": False,
                "client_type": row["CL_TYPE"] or None,
                "demo": True,
                "revenue_threshold": LARGE_BUSINESS_REVENUE,
            }
        )
        if len(rows) >= limit:
            break
    return tuple(rows)


@lru_cache(maxsize=1)
def dataset_counts() -> dict:
    large = below = empty = 0
    for row in load_uid_rows():
        revenue = _number(row["REVENUE_COMPANY"])
        if revenue is None:
            empty += 1
        elif revenue > LARGE_BUSINESS_REVENUE:
            large += 1
        else:
            below += 1
    return {"uid_rows": len(load_uid_rows()), "large": large, "below": below, "revenue_missing": empty}


@lru_cache(maxsize=1)
def load_users() -> tuple[dict, ...]:
    rows = [UserAccount.model_validate(item).model_dump() for item in _read_json("users.json")]
    _unique([row["id"] for row in rows], "пользователях")
    known = load_uid_index()
    for row in rows:
        if row["company_id"] not in known:
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
    load_links_by_uid.cache_clear()
    load_links_by_person.cache_clear()
    load_group_index.cache_clear()
    load_pay_index.cache_clear()
    load_uid_index.cache_clear()
    load_companies.cache_clear()
    company_by_id.cache_clear()
    excluded_preview.cache_clear()
    dataset_counts.cache_clear()
    load_users.cache_clear()
    load_news_seed.cache_clear()
    load_documents.cache_clear()
