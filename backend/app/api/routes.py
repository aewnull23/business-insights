import re

from fastapi import APIRouter, HTTPException, Query

from app.datasets import load_companies, load_documents, load_fid_rows, load_pay_rows, load_uid_rows
from app.providers.llm import llm_status
from app.schemas import QuestionIn
from app.services.agent import BriefingAgent, Forbidden, NotFound
from app.services.profile import excluded_companies, get_company, list_public, profile_view
from app.services.users import get_user, home_view, list_users
from app.sources.feed import collect_news
from app.storage.store import get_store

ID_RE = re.compile(r"^[a-z0-9-]{1,64}$")
AGENT = BriefingAgent()
router = APIRouter()


def parse_id(value: str) -> str:
    if not ID_RE.fullmatch(value):
        raise HTTPException(status_code=400, detail="bad id")
    return value


def _user_id(user_id: str | None) -> str | None:
    if not user_id:
        return None
    return parse_id(user_id)


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/status")
def status() -> dict:
    news, _, rss_error = collect_news()
    documents = load_documents()
    mode = llm_status()
    origins = {item["origin"] for item in news}
    return {
        "service": "alfa-business-insights",
        "news_mode": "mixed" if "rss" in origins else "demonstration",
        "rss_error": rss_error,
        "llm_mode": mode["mode"],
        "llm_model": mode["model"],
        "llm_note": mode["note"],
        "companies": len(load_companies()),
        "workspace_companies": len(list_public()),
        "documents": len(documents),
        "bank_documents": sum(1 for item in documents if item["is_bank_research"]),
        "uid_rows": len(load_uid_rows()),
        "fid_rows": len(load_fid_rows()),
        "pay_rows": len(load_pay_rows()),
        "data_note": "Профили собраны из синтетических CSV со схемой приложения 1. Оригинальные выгрузки организаторов в пакете проекта отсутствовали.",
    }


@router.get("/metrics")
def metrics() -> dict:
    snapshot = get_store().metrics()
    snapshot["monitoring"] = {
        "personalization": "доля сводок, где первая карточка меняется при смене компании или роли",
        "bank_coverage": "доля разборов, где найден материал с is_bank_research",
        "quality": "доля разборов с правкой quality gate",
        "ai": "число вызовов модели, отказов allowlist и отклоненных формулировок",
        "feedback": "уточняющие вопросы и ручная оценка эксперта на демо",
    }
    return snapshot


@router.get("/users")
def users() -> dict:
    return {"users": list_users()}


@router.get("/home")
def home(user_id: str = Query(..., min_length=2, max_length=64)) -> dict:
    parse_id(user_id)
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    company = get_company(user["company_id"])
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    return home_view(user, company)


@router.get("/companies")
def companies() -> dict:
    return {
        "companies": list_public(),
        "excluded": excluded_companies(),
        "threshold_rub": 15_000_000_000,
        "note": "В рабочем контуре крупного бизнеса — компании с выручкой свыше 15 млрд ₽ и явно помеченные неполные профили.",
    }


@router.get("/companies/{company_id}")
def company(company_id: str) -> dict:
    parse_id(company_id)
    found = get_company(company_id)
    if not found:
        raise HTTPException(status_code=404, detail="company not found")
    return profile_view(found)


@router.post("/companies/{company_id}/briefing")
def briefing(company_id: str, user_id: str | None = None) -> dict:
    parse_id(company_id)
    try:
        return AGENT.briefing(company_id, _user_id(user_id))
    except Forbidden:
        raise HTTPException(status_code=403, detail="user does not belong to company") from None
    except NotFound:
        raise HTTPException(status_code=404, detail="company not found") from None


@router.get("/companies/{company_id}/news/{news_id}")
def analysis(company_id: str, news_id: str, user_id: str | None = None) -> dict:
    parse_id(company_id)
    parse_id(news_id)
    try:
        return AGENT.analyze(company_id, news_id, _user_id(user_id))
    except Forbidden:
        raise HTTPException(status_code=403, detail="user does not belong to company") from None
    except NotFound:
        raise HTTPException(status_code=404, detail="not found") from None


@router.post("/companies/{company_id}/news/{news_id}/questions")
def ask(company_id: str, news_id: str, body: QuestionIn, user_id: str | None = None) -> dict:
    parse_id(company_id)
    parse_id(news_id)
    try:
        return AGENT.ask(company_id, news_id, body.question.strip(), _user_id(user_id))
    except Forbidden:
        raise HTTPException(status_code=403, detail="user does not belong to company") from None
    except NotFound:
        raise HTTPException(status_code=404, detail="not found") from None


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], include_in_schema=False)
def missing(path: str) -> None:
    raise HTTPException(status_code=404, detail="not found")
