import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import DATA_DIR, settings

LOGGER = logging.getLogger("app")
DESCRIPTION = """
Сервис новостной аналитики для руководителей крупного бизнеса в контуре интернет-банка Альфа-Бизнес.

Профили собираются из CSV со схемой приложения 1 кейса. Аналитика банка поднимается только из материалов с признаком `is_bank_research`. Выводы AI отделены от фактов источника.
"""


def create_app() -> FastAPI:
    app = FastAPI(
        title="Альфа-Бизнес · Новостная аналитика",
        description=DESCRIPTION,
        version="1.2.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.include_router(router, prefix="/api", tags=["insights"])
    # Expose only the research corpus, never profiles, payments or the runtime database.
    @app.get("/bank-pdfs/{filename}", include_in_schema=False)
    def bank_pdf(filename: str):
        from fastapi.responses import FileResponse

        root = (DATA_DIR / "bank_pdfs").resolve()
        target = (root / filename).resolve()
        if target.parent != root or target.suffix.lower() != ".pdf" or not target.is_file():
            raise HTTPException(status_code=404, detail="document not found")
        return FileResponse(target, media_type="application/pdf")

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
