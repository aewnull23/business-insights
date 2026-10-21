import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import settings

LOGGER = logging.getLogger("app")
DESCRIPTION = """
Сервис новостной аналитики для руководителей крупного бизнеса в контуре интернет-банка Альфа-Бизнес.

Профили собираются из CSV со схемой приложения 1 кейса. Аналитика банка поднимается только из материалов с признаком `is_bank_research`. Выводы AI отделены от фактов источника.
"""


def create_app() -> FastAPI:
    app = FastAPI(
        title="Альфа-Бизнес · Новостная аналитика",
        description=DESCRIPTION,
        version="1.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.include_router(router, prefix="/api", tags=["insights"])

    @app.exception_handler(Exception)
    async def unhandled(_request, exc):
        if isinstance(exc, HTTPException):
            return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
        LOGGER.error("unhandled %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"error": "internal_error"})

    frontend = Path(settings().frontend_dir)
    if frontend.exists():
        app.mount("/", StaticFiles(directory=str(frontend), html=True), name="ui")
    return app


app = create_app()
