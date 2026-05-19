"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger
from slowapi.errors import RateLimitExceeded

from app import __version__
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.license_key import warn_on_startup as warn_on_license_startup
from app.core.logging import configure_logging
from app.core.rate_limit import limiter, rate_limit_handler
from app.db.init_db import init_db
from app.services.housekeeping import run_now_safely as run_housekeeping, start_scheduler, stop_scheduler
from app.services.search_index import register_search_listeners


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    logger.info("Starting {} v{} ({}@{})", settings.app_name, __version__, settings.app_env, settings.db_backend)
    init_db()
    register_search_listeners()
    warn_on_license_startup()
    run_housekeeping()
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description="Offline-first business management + AI coding assistant.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
# NOTE: SlowAPIMiddleware + the @limiter.limit decorator currently break FastAPI's
# body-parameter detection (issue with how slowapi wraps signatures). Rate limiting
# is wired through `limiter` and can be enforced per-endpoint via a Depends-based
# guard if needed; the middleware is intentionally NOT installed.

register_exception_handlers(app)
app.include_router(api_router, prefix="/api/v1")

# Serve uploaded files (e.g., logos, attachments) — protected at the router level
app.mount("/files", StaticFiles(directory=str(settings.storage_dir / "uploads"), check_dir=False), name="files")


@app.get("/api/health", tags=["meta"])
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": __version__,
        "env": settings.app_env,
        "db_backend": settings.db_backend,
    }


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
