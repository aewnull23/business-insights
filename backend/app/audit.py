import logging

LOGGER = logging.getLogger("audit")


def record(
    tool: str,
    company_id: str | None = None,
    news_id: str | None = None,
    status: str = "ok",
    user_id: str | None = None,
) -> None:
    LOGGER.info(
        "tool=%s company=%s news=%s user=%s status=%s",
        tool,
        company_id or "-",
        news_id or "-",
        user_id or "-",
        status,
    )
    from app.storage.store import get_store

    get_store().add_audit(tool, company_id, news_id, status, user_id)
