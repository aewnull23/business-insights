import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import settings

LOGGER = logging.getLogger("app")


def create_app() -> FastAPI:
    app = FastAPI(title="Бизнес-инсайты")
    app.include_router(router, prefix="/api")

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
