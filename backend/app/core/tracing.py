"""OpenTelemetry tracing — opt-in OTLP exporter wiring.

Tracing is **off by default**. It is turned on when ``OTEL_EXPORTER_OTLP_ENDPOINT``
is set to a valid HTTP collector URL (e.g. ``http://otel-collector:4318``). With
no endpoint, every entry point in this module is a no-op so dev runs, tests,
and frozen builds don't try to push spans.

Why opt-in only:

* In offline / packaged deployments the customer may have no collector.
* Tests should not start a background BatchSpanProcessor.
* Spinning up SDK on every uvicorn reload doubles startup time.
"""
from __future__ import annotations

import os

from loguru import logger

from app import __version__
from app.core.config import settings

# Module-level flag so the public ``is_enabled`` helper doesn't need to
# re-read the env on every check.
_ENABLED = False

# Routes that should never produce spans. ``/metrics`` would dwarf real traffic
# (scrape every 15s), ``/api/health`` is a kubernetes liveness probe, the
# embeddable widget and the public marketing site are browsed by unauth
# visitors and would explode span volume.
EXCLUDED_URLS = "/metrics,/api/health,/widget.js,/site"


def _build_resource():  # type: ignore[no-untyped-def]
    from opentelemetry.sdk.resources import Resource

    return Resource.create(
        {
            "service.name": os.environ.get("OTEL_SERVICE_NAME", "enterprisecore-backend"),
            "service.version": __version__,
            "deployment.environment": settings.app_env,
        }
    )


def setup_tracing(app=None, engine=None) -> bool:  # type: ignore[no-untyped-def]
    """Configure OTel only if ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set.

    Returns ``True`` if tracing was actually wired up, ``False`` otherwise.

    Arguments:
        app: the FastAPI instance to instrument. May be ``None`` to defer
             instrumentation when the app object is not yet available.
        engine: the SQLAlchemy engine to instrument. May be ``None`` to skip
                DB instrumentation (useful in test runs).
    """
    global _ENABLED

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception as exc:  # pragma: no cover - import-guard for partial installs
        logger.warning("OpenTelemetry SDK unavailable; tracing disabled ({})", exc)
        return False

    provider = TracerProvider(resource=_build_resource())
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)

    # ---- FastAPI ----
    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app, excluded_urls=EXCLUDED_URLS)
        except Exception as exc:  # pragma: no cover
            logger.warning("FastAPI instrumentation failed: {}", exc)

    # ---- SQLAlchemy ----
    if engine is not None:
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

            SQLAlchemyInstrumentor().instrument(engine=engine)
        except Exception as exc:  # pragma: no cover
            logger.warning("SQLAlchemy instrumentation failed: {}", exc)

    # ---- HTTPX ----
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except Exception as exc:  # pragma: no cover
        logger.warning("HTTPX instrumentation failed: {}", exc)

    _ENABLED = True
    logger.info("OpenTelemetry tracing enabled → {}", endpoint)
    return True


def is_enabled() -> bool:
    """True if :func:`setup_tracing` previously installed an exporter."""
    return _ENABLED


__all__ = ["EXCLUDED_URLS", "is_enabled", "setup_tracing"]
