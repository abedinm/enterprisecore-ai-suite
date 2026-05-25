"""RQ worker entry point.

Usage::

    REDIS_URL=redis://localhost:6379/0 python scripts/run_worker.py

Listens on the three priority queues (``high`` → ``default`` → ``low``)
in that order so a quick AI follow-up doesn't get stuck behind a 2-hour
CSV import.

If ``REDIS_URL`` is not set this script exits 0 immediately so a
docker-compose unit can be wired up unconditionally.

Honours::

* ``REDIS_URL`` — connection string (required to do anything).
* ``LOG_FORMAT=json`` — switches the logger to JSON output for
  structured log shipping (Loki / DataDog).
* ``SENTRY_DSN`` — initialises Sentry for unhandled exceptions in the
  worker process.
* ``RQ_WORKER_NAME`` — overrides the worker name shown in monitoring.

Graceful shutdown: RQ already handles SIGTERM/SIGINT — it finishes the
current job then exits. We just install a logger hook so the operator
sees "worker shutting down".
"""
from __future__ import annotations

import logging
import os
import signal
import sys


def _configure_logging() -> None:
    fmt = os.environ.get("LOG_FORMAT", "text").lower()
    if fmt == "json":
        # Tiny inline JSON formatter so we don't add a dep just for this.
        import json as _json

        class _Json(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:  # noqa: D401
                payload = {
                    "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
                    "level": record.levelname,
                    "name": record.name,
                    "msg": record.getMessage(),
                }
                if record.exc_info:
                    payload["exc"] = self.formatException(record.exc_info)
                return _json.dumps(payload)

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_Json())
        root = logging.getLogger()
        root.handlers = [handler]
        root.setLevel(logging.INFO)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )


def _maybe_init_sentry() -> None:
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk  # type: ignore[import-not-found]

        sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0)
        logging.getLogger(__name__).info("Sentry initialised for worker")
    except Exception:
        logging.getLogger(__name__).exception("Sentry init failed")


def _install_shutdown_logger() -> None:
    log = logging.getLogger(__name__)

    def _handler(signum, _frame):
        log.info("worker received signal %s, will exit after current job", signum)
        # Don't actually exit here — RQ's own SimpleWorker handler does that
        # cleanly after the current burst finishes.

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            # SIGTERM unavailable on Windows in some contexts; ignore.
            pass


def main() -> int:
    _configure_logging()
    log = logging.getLogger(__name__)

    url = os.environ.get("REDIS_URL")
    if not url:
        log.warning(
            "REDIS_URL not set — worker has nothing to do, exiting cleanly. "
            "Set REDIS_URL to point at a Redis instance to enable async jobs."
        )
        return 0

    try:
        import redis  # type: ignore[import-not-found]
        from rq import Queue, Worker  # type: ignore[import-not-found]
    except ImportError:
        log.error(
            "rq and/or redis not installed. Install with: "
            "pip install 'rq>=1.16' 'redis>=5.0'"
        )
        return 1

    _maybe_init_sentry()
    _install_shutdown_logger()

    conn = redis.Redis.from_url(url)
    queues = [Queue("high", connection=conn),
              Queue("default", connection=conn),
              Queue("low", connection=conn)]
    name = os.environ.get("RQ_WORKER_NAME")
    worker = Worker(queues, connection=conn, name=name)
    log.info(
        "RQ worker starting; listening on %s",
        ", ".join(q.name for q in queues),
    )
    worker.work(with_scheduler=False)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
