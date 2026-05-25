"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from slowapi.errors import RateLimitExceeded

from app import __version__
from app.api.v1.endpoints.marketing_site import router as marketing_site_router
from app.api.v1.endpoints.stripe_webhook import router as stripe_webhook_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.csrf import CSRFMiddleware
from app.core.exceptions import register_exception_handlers
from app.core.license_key import warn_on_startup as warn_on_license_startup
from app.core.logging import configure_logging
from app.core.metrics import render_latest, set_build_info
from app.core.observability import PrometheusMiddleware, RequestIDMiddleware
from app.core.rate_limit import RateLimit, limiter, rate_limit_handler
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.sentry import init_sentry
from app.core.ip_allowlist import IPAllowlistMiddleware
from app.core.tenant_middleware import TenantMiddleware
from app.core.tenant_orm import install_tenant_orm_hooks
from app.core.tracing import setup_tracing
from app.db.init_db import init_db
from app.db.session import engine as db_engine
from app.services.audit_streamer import start as start_audit_streamer, stop as stop_audit_streamer
from app.services.housekeeping import run_now_safely as run_housekeeping, start_scheduler, stop_scheduler
from app.services.search_index import register_search_listeners

# Install the tenant ORM event hooks as soon as this module imports — they
# need to be in place before any request opens a Session. Idempotent.
install_tenant_orm_hooks()


@asynccontextmanager
async def lifespan(app_: FastAPI):
    configure_logging()
    init_sentry()
    # OTel tracing only spins up when OTEL_EXPORTER_OTLP_ENDPOINT is set;
    # otherwise this is a cheap no-op. Wired in lifespan so tests don't pay
    # for it.
    setup_tracing(app=app_, engine=db_engine)
    # build_info gauge — emit once so dashboards can stitch series to a
    # specific release.
    import os
    set_build_info(
        version=__version__,
        commit=os.environ.get("GIT_COMMIT", "unknown"),
        env=settings.app_env,
    )
    logger.info("Starting {} v{} ({}@{})", settings.app_name, __version__, settings.app_env, settings.db_backend)
    init_db()
    register_search_listeners()
    # Wire third-party integrations + the workflow engine into the event bus.
    # Both calls are idempotent — they unsubscribe-then-subscribe so multiple
    # lifespan re-entries (tests, reloads) don't fan an event out twice.
    from app.services.integrations import register_all_subscribers as _reg_integrations
    from app.services.workflow_engine import register_subscribers as _reg_workflows
    _reg_integrations()
    _reg_workflows()
    warn_on_license_startup()
    run_housekeeping()
    start_scheduler()
    # Audit streamer — opt-in: only spins up when a destination has been
    # configured. The start() helper is idempotent and safe to call here
    # unconditionally; the loop will simply find no active destinations
    # on each pass for tenants that haven't configured one.
    if os.environ.get("AUDIT_STREAMER_ENABLED", "true").lower() != "false":
        start_audit_streamer()
    yield
    stop_audit_streamer()
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

# Security headers — registered AFTER CORS so it executes earlier on the
# request leg (Starlette stacks middleware in reverse-add order) and later
# on the response leg, i.e. CORS still runs first when the response starts
# but our headers wrap the final outgoing message. Path-aware exceptions
# for /site/* and /widget.js live inside the middleware itself.
app.add_middleware(SecurityHeadersMiddleware)

# IP allowlist — added BEFORE TenantMiddleware in code order so it runs
# AFTER it on the inbound leg (Starlette stacks in reverse-add order).
# That ordering matters because the allowlist middleware reads the
# active tenant from the contextvar set by TenantMiddleware. Bypass
# rules for /api/health, /metrics, /widget.js, /site/*, /api/v1/auth/*
# live inside the middleware itself.
app.add_middleware(IPAllowlistMiddleware)

# Tenant middleware — reads the JWT, looks up the user's tenant_id, and
# puts it on a ContextVar so the auto-filter in tenant_orm.py can scope
# every ORM query for the rest of the request. Added BEFORE the metrics +
# request-id middlewares so the contextvar is set when those frames log.
app.add_middleware(TenantMiddleware)

# CSRF middleware — enforces double-submit cookie on cookie-authenticated
# mutating requests. Bearer-token / API-client requests pass through. We
# disable it in the test client by default via ``ENTERPRISECORE_DISABLE_CSRF``
# so the existing pytest suite (which uses Bearer headers) stays green; real
# browser sessions go through the full check.
import os as _os_for_csrf  # noqa: E402
_csrf_enabled = _os_for_csrf.environ.get("ENTERPRISECORE_DISABLE_CSRF", "").lower() not in ("1", "true", "yes")
app.add_middleware(CSRFMiddleware, enabled=_csrf_enabled)

# Prometheus + RequestID. Starlette stacks middlewares in reverse-add order,
# so the LAST one added runs first on the inbound leg. We want
# RequestIDMiddleware outermost (so request_id is set before any subsequent
# middleware logs), and PrometheusMiddleware just inside it (so it measures
# the full handler time including security headers + CORS).
app.add_middleware(PrometheusMiddleware)
app.add_middleware(RequestIDMiddleware)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
# NOTE: SlowAPIMiddleware + the @limiter.limit decorator currently break FastAPI's
# body-parameter detection (issue with how slowapi wraps signatures). Rate limiting
# is wired through `limiter` and can be enforced per-endpoint via a Depends-based
# guard if needed; the middleware is intentionally NOT installed.

register_exception_handlers(app)
app.include_router(api_router, prefix="/api/v1")

# Realtime — WebSocket endpoints. Mounted on the FastAPI app directly
# (not behind the api_router) because middlewares that wrap HTTP requests
# don't always cooperate with the WebSocket scope; keeping these on the
# root surface makes the auth handshake easier to reason about. Tenant
# scoping is enforced inside each endpoint via the JWT in the handshake.
from app.api.v1.endpoints.ws import router as ws_router  # noqa: E402
app.include_router(ws_router, prefix="/api/v1", tags=["realtime"])

# Marketing Site Builder — public rendered site. Lives at /site (NOT under
# /api/v1) so the URLs are clean for visitors. Plan-gated, no auth required.
app.include_router(marketing_site_router, prefix="/site")

# Stripe webhook — public, signature-verified. Lives at /stripe/webhook
# (NOT under /api/v1) so the URL is stable and easy to paste into the
# Stripe Dashboard.
app.include_router(stripe_webhook_router, prefix="/stripe", tags=["stripe"])

# SCIM 2.0 protocol surface — mounted at the application root (NOT under
# /api/v1) because SCIM clients (Okta, Azure AD, JumpCloud) hard-code
# ``/scim/v2/Users`` and ``/scim/v2/Groups`` per RFC 7644 §3.1. Auth is
# the SCIM bearer token in the Authorization header, NOT a JWT — each
# token is bound to a single tenant inside the endpoint code.
from app.api.v1.endpoints.scim import scim_router  # noqa: E402
app.include_router(scim_router, prefix="/scim/v2", tags=["scim"])

# Serve uploaded files (e.g., logos, attachments) — protected at the router level
app.mount("/files", StaticFiles(directory=str(settings.storage_dir / "uploads"), check_dir=False), name="files")

# Embeddable web-chat widget. Served from /widget.js so customers can drop a single
# <script src="https://<host>/widget.js" data-bot-id="..."> tag onto any site.
# CORS is permissive on this static asset only; the public chat endpoint manages
# its own CORS separately.
WIDGET_PATH = Path(__file__).parent / "static" / "widget.js"


@app.api_route("/widget.js", methods=["GET", "HEAD"], include_in_schema=False)
def serve_widget():
    return FileResponse(
        WIDGET_PATH,
        media_type="application/javascript",
        headers={
            "Cache-Control": "public, max-age=300",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.get("/api/health", tags=["meta"])
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": __version__,
        "env": settings.app_env,
        "db_backend": settings.db_backend,
    }


# Public status page — mounts at /status and /status.html. Never requires
# auth so external monitors (Pingdom, Better Uptime, etc.) and customers
# can read it without a token.
from app.api.v1.endpoints.status import router as status_router  # noqa: E402
app.include_router(status_router, prefix="/status", tags=["status"])


# Prometheus exposition endpoint. Mounted at the app root (NOT under /api/v1)
# so scrapers don't need to know the API prefix. Public — Prometheus does not
# carry auth — but rate-limited per IP so a hostile scanner can't exhaust the
# process by hammering it.
@app.get(
    "/metrics",
    include_in_schema=False,
    dependencies=[Depends(RateLimit("60/minute", id="metrics"))],
)
def metrics() -> Response:
    body, content_type = render_latest()
    return Response(content=body, media_type=content_type)


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
