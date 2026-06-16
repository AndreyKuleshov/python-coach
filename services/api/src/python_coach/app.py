"""FastAPI application factory and ASGI entrypoint.

Wires routers, structured logging, and serves the minimal frontend lesson page
as static files. Run with: uvicorn python_coach.app:app
"""

from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from python_coach.transport.rest.lessons.routes import router as lessons_router
from python_coach.transport.rest.progress.routes import router as progress_router
from python_coach.transport.rest.submissions.routes import router as submissions_router

# static/ ships the single-page lesson UI; resolved relative to the installed package.
_STATIC_DIR = Path(__file__).resolve().parents[2] / "static"


def _configure_logging() -> None:
    """Configure structlog for JSON output; services never use print."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )


def create_app() -> FastAPI:
    """Build the FastAPI app with routers and the static lesson page mounted."""
    _configure_logging()
    app = FastAPI(title="python-coach", version="0.1.0")

    app.include_router(lessons_router)
    app.include_router(submissions_router)
    app.include_router(progress_router)

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok"}

    if _STATIC_DIR.is_dir():

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            """Serve the single-page lesson UI."""
            return FileResponse(_STATIC_DIR / "index.html")

        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    return app


app = create_app()
