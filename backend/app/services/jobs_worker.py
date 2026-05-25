"""Worker-side helpers for the RQ background job system.

The main worker entry point is :func:`app.services.jobs._worker_entry` —
RQ calls it with the Job row id, tenant id, dotted function name, and
the serialised args/kwargs. This thin module re-exports it under a more
discoverable name and adds two utilities the operator-facing worker
script and the in-process test harness both use.

Keep this module free of FastAPI imports so it can be loaded by the
``rq worker`` process without booting the whole app.
"""
from __future__ import annotations

import logging
from typing import Any

from app.services.jobs import _worker_entry as _entry, get_queue

logger = logging.getLogger(__name__)


def run_job(
    job_id: str, tenant_id: str, function_name: str,
    args: list, kwargs: dict,
) -> Any:
    """Public, named alias for the worker entry point.

    Exists so the function on the worker side has a stable dotted path
    (``app.services.jobs_worker.run_job``) callers and external tools can
    pin to, separate from the private ``_worker_entry`` symbol.
    """

    return _entry(job_id, tenant_id, function_name, args, kwargs)


def drain_default_queue(max_jobs: int = 100) -> int:
    """Synchronously drain pending jobs on the default queue.

    Used by integration tests + small ops scripts. Returns the number of
    jobs processed. No-op if Redis isn't configured.
    """

    queue = get_queue()
    if queue is None:
        return 0
    try:
        from rq import SimpleWorker  # type: ignore[import-not-found]
    except ImportError:
        return 0
    worker = SimpleWorker([queue], connection=queue.connection)
    worker.work(burst=True, max_jobs=max_jobs)
    return max_jobs
