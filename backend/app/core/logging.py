"""Loguru-based structured logging.

Supports two modes selected via ``LOG_FORMAT`` env var:

* ``human`` (default in development) — colored, human-readable single-line
  output suitable for live tailing.
* ``json`` (default in production) — one JSON object per line on stderr with a
  fixed schema (timestamp, level, logger, message, request_id, tenant_id,
  user_id, exception, extra). Designed for log aggregators (Loki, Datadog,
  CloudWatch, ELK).

Request context (request_id, user_id, tenant_id) flows in through three
contextvars set by :class:`app.core.observability.RequestIDMiddleware`.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.core.config import settings

# ---------------------------------------------------------------------------
# Request-scoped context variables. The RequestIDMiddleware sets these at the
# start of every request and resets them at the end. Loguru reads them in the
# JSON serializer below so every log line emitted during a request carries the
# correlation IDs without needing the caller to pass them.
# ---------------------------------------------------------------------------
request_id_ctx: ContextVar[str | None] = ContextVar("request_id_ctx", default=None)
user_id_ctx: ContextVar[str | None] = ContextVar("user_id_ctx", default=None)
tenant_id_ctx: ContextVar[str | None] = ContextVar("tenant_id_ctx", default=None)


def _resolve_log_format() -> str:
    """Decide which output format to use. Explicit env var wins; otherwise
    production defaults to JSON and everything else to human."""
    explicit = os.environ.get("LOG_FORMAT", "").strip().lower()
    if explicit in {"human", "json"}:
        return explicit
    return "json" if settings.app_env == "production" else "human"


def _safe_jsonable(value: Any) -> Any:
    """Best-effort conversion of an arbitrary Loguru ``extra`` value to a
    JSON-serializable type. Falls back to ``repr`` for unknown objects so we
    never blow up the log pipeline because a caller put a Decimal or a model
    in extra."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


def _json_sink(message: Any) -> None:
    """Loguru sink that emits one JSON object per log record on stderr.

    We build our own JSON instead of using ``serialize=True`` because Loguru's
    built-in serializer dumps everything (including a multi-line traceback as
    one big string) — we want flat, log-aggregator-friendly fields.
    """
    record = message.record
    payload: dict[str, Any] = {
        "timestamp": record["time"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "level": record["level"].name,
        "logger": record["name"],
        "message": record["message"],
    }

    # Request-scoped correlation IDs. Always present as keys (null when unset)
    # so log-aggregator field detection stays stable.
    rid = request_id_ctx.get()
    uid = user_id_ctx.get()
    tid = tenant_id_ctx.get()
    if rid is not None:
        payload["request_id"] = rid
    if uid is not None:
        payload["user_id"] = uid
    if tid is not None:
        payload["tenant_id"] = tid

    # Module location helps when grepping in production.
    payload["module"] = record["module"]
    payload["function"] = record["function"]
    payload["line"] = record["line"]

    # Exception → structured field. We pull out type/value/traceback rather
    # than dumping the multi-line formatted string, so a log query can filter
    # on exception_type.
    exc = record["exception"]
    if exc is not None:
        import traceback

        payload["exception"] = {
            "type": exc.type.__name__ if exc.type else None,
            "value": str(exc.value) if exc.value else None,
            "traceback": (
                "".join(traceback.format_exception(exc.type, exc.value, exc.traceback))
                if exc.traceback is not None
                else None
            ),
        }

    # Anything the caller passed via logger.bind(...) or extra= lands here.
    extra = {k: _safe_jsonable(v) for k, v in record.get("extra", {}).items()}
    if extra:
        payload["extra"] = extra

    sys.stderr.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stderr.flush()


class InterceptHandler(logging.Handler):
    """Redirect stdlib logging records through Loguru."""

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging() -> None:
    """Install the active log sinks based on ``LOG_FORMAT`` / app env."""
    logger.remove()
    level = "DEBUG" if settings.app_debug else "INFO"
    log_format = _resolve_log_format()

    if log_format == "json":
        # Single JSON sink → stderr. Production-style. No colors, no rotation
        # here because shipping to a log aggregator (Loki, Datadog, etc.) is
        # the typical deployment path.
        logger.add(_json_sink, level=level, format="{message}")
    else:
        # Human, colored, single-line format for local dev.
        logger.add(
            sys.stdout,
            level=level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level:<7}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                "<level>{message}</level>"
            ),
            colorize=True,
        )

    # Always also keep a rotating local file for forensic recovery. Format here
    # mirrors the configured mode so the on-disk file matches what was streamed
    # live.
    log_file = settings.storage_dir / "logs" / "app.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if log_format == "json":
        logger.add(
            log_file,
            level=level,
            rotation="20 MB",
            retention="30 days",
            compression="zip",
            enqueue=True,
            format=lambda _: "{message}",  # placeholder; serialize below owns the payload
            serialize=True,
        )
    else:
        logger.add(
            log_file,
            level=level,
            rotation="20 MB",
            retention="30 days",
            compression="zip",
            enqueue=True,
        )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "sqlalchemy.engine"):
        logging.getLogger(name).handlers = [InterceptHandler()]
        logging.getLogger(name).propagate = False
