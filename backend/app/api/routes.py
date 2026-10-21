import re

from fastapi import APIRouter, HTTPException

from app.datasets import load_companies, load_documents
from app.providers.llm import llm_status
from app.schemas import QuestionIn
from app.services.agent import BriefingAgent, NotFound
from app.services.profile import get_company, list_public, profile_view
from app.sources.feed import collect_news

ID_RE = re.compile(r"^[a-z0-9-]{1,64}$")
AGENT = BriefingAgent()
router = APIRouter()


def parse_id(value: str) -> str:
    if not ID_RE.fullmatch(value):
        raise HTTPException(status_code=400, detail="bad id")
    return value


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
        "service": "business-insights",
        "news_mode": "mixed" if "rss" in origins else "demonstration",
        "rss_error": rss_error,
        "llm_mode": mode["mode"],
        "llm_model": mode["model"],
        "llm_note": mode["note"],
        "companies": len(load_companies()),
        "documents": len(documents),
        "bank_documents": sum(1 for item in documents if item["is_bank_research"]),
    }


@router.get("/companies")
def companies() -> dict:
    return {"companies": list_public()}


@router.get("/companies/{company_id}")
def company(company_id: str) -> dict:
    parse_id(company_id)
    found = get_company(company_id)
    if not found:
        raise HTTPException(status_code=404, detail="company not found")
    return profile_view(found)


@router.post("/companies/{company_id}/briefing")
def briefing(company_id: str) -> dict:
    parse_id(company_id)
    try:
        return AGENT.briefing(company_id)
    except NotFound:
        raise HTTPException(status_code=404, detail="company not found") from None


@router.get("/companies/{company_id}/news/{news_id}")
def analysis(company_id: str, news_id: str) -> dict:
    parse_id(company_id)
    parse_id(news_id)
    try:
        return AGENT.analyze(company_id, news_id)
    except NotFound:
        raise HTTPException(status_code=404, detail="not found") from None


@router.post("/companies/{company_id}/news/{news_id}/questions")
def ask(company_id: str, news_id: str, body: QuestionIn) -> dict:
    parse_id(company_id)
    parse_id(news_id)
    try:
        return AGENT.ask(company_id, news_id, body.question.strip())
    except NotFound:
        raise HTTPException(status_code=404, detail="not found") from None


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def missing(path: str) -> None:
    raise HTTPException(status_code=404, detail="not found")
