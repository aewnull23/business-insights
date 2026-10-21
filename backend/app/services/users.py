from app.datasets import load_users
from app.services.profile import get_company


ROLE_BOOST = {
    "генеральный директор": 1.15,
    "собственник бизнеса": 1.2,
    "финансовый директор": 1.45,
    "руководитель казначейства": 1.6,
    "главный бухгалтер": 1.55,
}


def list_users() -> list[dict]:
    rows = []
    for user in load_users():
        company = get_company(user["company_id"])
        rows.append(
            {
                **user,
                "company_name": None if not company else company["name"],
                "industry": None if not company else company.get("industry"),
                "large_business": False if not company else company.get("large_business"),
            }
        )
    return rows


def get_user(user_id: str | None) -> dict | None:
    if not user_id:
        return None
    for user in load_users():
        if user["id"] == user_id:
            return dict(user)
    return None


def default_user(company_id: str) -> dict | None:
    for user in load_users():
        if user["company_id"] == company_id:
            return dict(user)
    return None


def topic_boosts(user: dict | None) -> dict[str, float]:
    if not user:
        return {}
    factor = ROLE_BOOST.get(user.get("role") or "", 1.25)
    return {topic: factor for topic in user.get("focus_topics") or []}


def home_view(user: dict, company: dict) -> dict:
    products = company.get("bank_products") or []
    return {
        "user": {
            "id": user["id"],
            "role": user["role"],
            "display_name": user["display_name"],
        },
        "company": {
            "id": company["id"],
            "name": company["name"],
            "industry": company.get("industry"),
            "city": company.get("city"),
            "large_business": company.get("large_business"),
            "client_type": company.get("client_type"),
        },
        "accounts": [
            {
                "name": "Расчетный счет ₽",
                "status": "демо-виджет интернет-банка",
                "note": "Остаток не берется из датасета кейса и не используется в инсайтах.",
            }
        ],
        "products": products,
        "entry": {
            "id": "insights",
            "title": "Новостная аналитика",
            "lead": "События, которые относятся к этой компании, с фактами, позицией банка и выводами AI.",
            "always_visible": True,
        },
    }
