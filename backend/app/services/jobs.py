"""Background-job queue service.

A thin façade over RQ (Redis Queue) with a transparent synchronous
fallback for installations that don't run a separate worker process —
notably the test suite and small self-host installs where the operator
hasn't set ``REDIS_URL``.

Design goals
------------

1. **Same call site in both modes.** Endpoint code calls
   ``enqueue_or_run(fn, *args)`` and gets back a :class:`JobHandle`. In
   Redis mode, RQ runs the function on a worker; in sync mode, the
   function runs immediately on the caller's thread. Either way the
   caller gets an id it can poll.

2. **Every job is tenant-scoped.** The current tenant id is captured at
   enqueue time and re-applied on the worker side via
   :func:`tenant_scope` so the auto-filter behaves identically to a
   normal HTTP request.

3. **DB-tracked observability.** Each enqueue creates a :class:`Job`
   row (separate from RQ's redis-only state) so the admin UI can query
   "what ran for *my* tenant this week" without touching Redis.

4. **No hard dep on Redis/RQ.** If ``REDIS_URL`` is not set we never
   import ``redis`` or ``rq``. Tests and clean-install dev sessions
   don't need either package.
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant_context import (
    bypass_tenant_filter,
    get_current_tenant_id,
    tenant_scope,
)
from app.db.session import SessionLocal
from app.models.jobs import Job, JobAttempt

logger = logging.getLogger(__name__)


# Queue names — match what scripts/run_worker.py listens on.
QUEUE_DEFAULT = "default"
QUEUE_HIGH = "high"
QUEUE_LOW = "low"
VALID_QUEUES = {QUEUE_DEFAULT, QUEUE_HIGH, QUEUE_LOW}


# ---------------------------------------------------------------------------
# JobHandle — the surface every enqueue returns. Same shape sync vs async so
# callers don't branch on the mode.
# ---------------------------------------------------------------------------

@dataclass
class JobHandle:
    """Returned by :func:`enqueue_or_run`.

    ``job_id`` is the DB row id — *not* the RQ job id. Callers poll
    ``GET /api/v1/jobs/{id}`` with this. ``mode`` is ``"redis"`` or
    ``"sync"``; mostly useful for tests that want to assert which path ran.
    """

    job_id: str
    mode: str
    status: str
    result: Any = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Mode detection. Cached so test runs that set/unset REDIS_URL recompute.
# ---------------------------------------------------------------------------

def _redis_url() -> str | None:
    """Read REDIS_URL from env on every call so tests can flip it."""

    return os.environ.get("REDIS_URL") or None


# Module-level overrides so tests can substitute a fake Redis connection
# without touching env vars.
_redis_conn_override = None
_queue_override = None


def set_redis_connection(conn) -> None:
    """Tests call this to substitute a fake Redis. ``None`` clears it."""

    global _redis_conn_override
    _redis_conn_override = conn


def set_queue_override(queue) -> None:
    """Tests call this to substitute a fake RQ Queue. ``None`` clears it."""

    global _queue_override
    _queue_override = queue


def _get_redis_connection():
    """Return a redis connection, or None if Redis isn't configured.

    We import lazily so the redis dep is only required when the operator
    actually wants async job execution.
    """

    if _redis_conn_override is not None:
        return _redis_conn_override
    url = _redis_url()
    if not url:
        return None
    try:
        import redis  # type: ignore[import-not-found]

        return redis.Redis.from_url(url)
    except Exception:
        logger.exception("Could not connect to Redis at %s", url)
        return None


def get_queue(name: str = QUEUE_DEFAULT):
    """Return an RQ Queue object, or None if running in sync mode.

    Callers that only want to *know* whether async mode is on can check
    ``get_queue() is not None``.
    """

    if name not in VALID_QUEUES:
        raise ValueError(f"Unknown queue name: {name}. Valid: {sorted(VALID_QUEUES)}")
    if _queue_override is not None:
        return _queue_override
    conn = _get_redis_connection()
    if conn is None:
        return None
    try:
        from rq import Queue  # type: ignore[import-not-found]

        return Queue(name, connection=conn)
    except Exception:
        logger.exception("Could not construct RQ Queue %s", name)
        return None


def is_async_enabled() -> bool:
    """True iff Redis is reachable + RQ can be imported."""

    return get_queue() is not None


# ---------------------------------------------------------------------------
# Function-name resolution. We store the dotted import path on the Job row
# so the worker can re-import + call it, and so the admin UI can group by it.
# ---------------------------------------------------------------------------

def _func_dotted(fn: Callable) -> str:
    """Return ``module.qualname`` for ``fn``."""

    mod = getattr(fn, "__module__", "?")
    qn = getattr(fn, "__qualname__", getattr(fn, "__name__", "?"))
    return f"{mod}.{qn}"


def _resolve_dotted(dotted: str) -> Callable:
    """Inverse of ``_func_dotted``. Used by the worker entry point."""

    if "." not in dotted:
        raise ValueError(f"Cannot resolve {dotted!r}: not a dotted path")
    module_name, _, qualname = dotted.rpartition(".")
    mod = importlib.import_module(module_name)
    target: Any = mod
    for part in qualname.split("."):
        target = getattr(target, part)
    if not callable(target):
        raise TypeError(f"{dotted} is not callable")
    return target


# ---------------------------------------------------------------------------
# Args serialisation. We JSON-encode args/kwargs for the DB row so the admin
# UI can render them. Non-serialisable args (DB sessions, file objects) are
# replaced with a placeholder.
# ---------------------------------------------------------------------------

def _safe_jsonable(args: tuple, kwargs: dict) -> dict:
    def _coerce(v: Any) -> Any:
        try:
            json.dumps(v, default=str)
            return v
        except Exception:
            return f"<{type(v).__name__}>"

    return {
        "args": [_coerce(a) for a in args],
        "kwargs": {k: _coerce(v) for k, v in kwargs.items()},
    }


# ---------------------------------------------------------------------------
# DB row helpers. All run with ``bypass_tenant_filter`` so the worker side
# (which has no inbound request) can still write/read across tenants.
# ---------------------------------------------------------------------------

def _create_job_row(
    *,
    function_name: str,
    args_json: dict,
    queue_name: str,
    tenant_id: str | None,
    created_by_id: str | None,
    rq_job_id: str | None,
    initial_status: str,
) -> Job:
    """Create the persistent Job row and return it.

    We need a tenant id on every row (NOT NULL on the column) — if the
    caller didn't pass one and there's no ambient tenant context, we
    cannot enqueue. Callers should be inside a request scope or pass
    ``tenant_id`` explicitly.
    """

    tid = tenant_id or get_current_tenant_id()
    if not tid:
        raise RuntimeError(
            "enqueue() called with no tenant context — pass tenant_id explicitly"
        )
    with SessionLocal() as db:
        with bypass_tenant_filter():
            row = Job(
                tenant_id=tid,
                function_name=function_name,
                args_json=args_json,
                status=initial_status,
                queue_name=queue_name,
                attempts=0,
                rq_job_id=rq_job_id,
                created_by_id=created_by_id,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            # Detach from session for return.
            db.expunge(row)
            return row


def _update_job(job_id: str, **fields) -> Job | None:
    with SessionLocal() as db, bypass_tenant_filter():
        row = db.get(Job, job_id)
        if not row:
            return None
        for k, v in fields.items():
            setattr(row, k, v)
        db.commit()
        db.refresh(row)
        db.expunge(row)
        return row


def _record_attempt(
    *, job_id: str, tenant_id: str, attempt_number: int,
    started: datetime, finished: datetime, status: str,
    error: str | None,
) -> None:
    duration_ms = int((finished - started).total_seconds() * 1000)
    with SessionLocal() as db, bypass_tenant_filter():
        db.add(JobAttempt(
            tenant_id=tenant_id,
            job_id=job_id,
            attempt_number=attempt_number,
            status=status,
            started_at=started,
            finished_at=finished,
            duration_ms=duration_ms,
            error_message=error,
        ))
        db.commit()


# ---------------------------------------------------------------------------
# Public enqueue surface.
# ---------------------------------------------------------------------------

def enqueue(
    fn: Callable,
    *args,
    tenant_id: str | None = None,
    queue: str = QUEUE_DEFAULT,
    created_by_id: str | None = None,
    **kwargs,
) -> JobHandle:
    """Enqueue ``fn(*args, **kwargs)`` onto the RQ queue.

    Returns immediately with a :class:`JobHandle` whose ``status`` is
    ``"queued"``. Callers can poll ``get_job_status(handle.job_id)`` to
    watch the transition. In **sync** mode (no Redis) this function
    runs the call inline and returns a handle whose status is already
    ``"completed"`` or ``"failed"``.

    ``tenant_id`` defaults to the current tenant context — pass it
    explicitly only when enqueuing from a background scheduler that
    has no ambient context.
    """

    function_name = _func_dotted(fn)
    args_json = _safe_jsonable(args, kwargs)
    tid = tenant_id or get_current_tenant_id()
    queue_obj = get_queue(queue)
    if queue_obj is None:
        return _run_sync(
            fn, args, kwargs,
            function_name=function_name, args_json=args_json,
            tenant_id=tid, queue=queue, created_by_id=created_by_id,
        )
    return _enqueue_redis(
        fn, args, kwargs, queue_obj,
        function_name=function_name, args_json=args_json,
        tenant_id=tid, queue=queue, created_by_id=created_by_id,
    )


# Friendly alias matching the wording in the design doc.
def enqueue_or_run(fn: Callable, *args, **kwargs) -> JobHandle:
    """Same as :func:`enqueue` — kept as the verb call sites use."""

    return enqueue(fn, *args, **kwargs)


def _run_sync(
    fn: Callable, args: tuple, kwargs: dict,
    *, function_name: str, args_json: dict,
    tenant_id: str | None, queue: str, created_by_id: str | None,
) -> JobHandle:
    """Synchronous execution — runs the function inline, records the row."""

    if not tenant_id:
        # In sync mode this still matters: the Job row needs a tenant.
        raise RuntimeError(
            "enqueue_or_run() called with no tenant context — "
            "wrap the call in tenant_scope() or pass tenant_id="
        )
    row = _create_job_row(
        function_name=function_name, args_json=args_json,
        queue_name=queue, tenant_id=tenant_id,
        created_by_id=created_by_id, rq_job_id=None,
        initial_status="running",
    )
    started = datetime.now(timezone.utc)
    _update_job(row.id, started_at=started, attempts=1)
    error: str | None = None
    result: Any = None
    try:
        with tenant_scope(tenant_id):
            result = fn(*args, **kwargs)
        status = "completed"
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync job %s (%s) raised", row.id, function_name)
        error = f"{type(exc).__name__}: {exc}"[:2000]
        status = "failed"
    finished = datetime.now(timezone.utc)
    excerpt = (str(result)[:500] if result is not None else None)
    _update_job(
        row.id,
        status=status,
        completed_at=finished,
        result_excerpt=excerpt,
        last_error=error,
    )
    _record_attempt(
        job_id=row.id, tenant_id=tenant_id, attempt_number=1,
        started=started, finished=finished, status=status, error=error,
    )
    return JobHandle(job_id=row.id, mode="sync", status=status, result=result, error=error)


def _enqueue_redis(
    fn: Callable, args: tuple, kwargs: dict, queue_obj,
    *, function_name: str, args_json: dict,
    tenant_id: str | None, queue: str, created_by_id: str | None,
) -> JobHandle:
    """Redis mode — push to RQ + write the Job row.

    The function the worker actually runs is :func:`_worker_entry`, which
    rebuilds the tenant context + calls the target. We pass enough info
    on RQ's side to look up the Job row + write its lifecycle updates.
    """

    if not tenant_id:
        raise RuntimeError(
            "enqueue_or_run() called with no tenant context — "
            "wrap the call in tenant_scope() or pass tenant_id="
        )
    row = _create_job_row(
        function_name=function_name, args_json=args_json,
        queue_name=queue, tenant_id=tenant_id,
        created_by_id=created_by_id, rq_job_id=None,
        initial_status="queued",
    )
    try:
        rq_job = queue_obj.enqueue(
            _worker_entry,
            row.id, tenant_id, function_name, list(args), kwargs,
            job_timeout=kwargs.pop("__job_timeout__", 600),
        )
        rq_job_id = getattr(rq_job, "id", None) or getattr(rq_job, "job_id", None)
        _update_job(row.id, rq_job_id=rq_job_id)
        return JobHandle(job_id=row.id, mode="redis", status="queued")
    except Exception as exc:  # noqa: BLE001
        logger.exception("RQ enqueue failed for %s", function_name)
        _update_job(
            row.id, status="failed",
            last_error=f"enqueue error: {type(exc).__name__}: {exc}"[:2000],
            completed_at=datetime.now(timezone.utc),
        )
        return JobHandle(
            job_id=row.id, mode="redis", status="failed",
            error=f"{type(exc).__name__}: {exc}",
        )


# ---------------------------------------------------------------------------
# Worker-side entry point. RQ calls this; we resolve the actual function,
# rebuild the tenant context, and write the Job/JobAttempt lifecycle rows.
# Importable as ``app.services.jobs._worker_entry``.
# ---------------------------------------------------------------------------

def _worker_entry(
    job_id: str, tenant_id: str, function_name: str,
    args: list, kwargs: dict,
) -> Any:
    """Called inside the RQ worker. NEVER call this from request code."""

    fn = _resolve_dotted(function_name)
    attempt = 1
    row = _update_job(job_id, status="running", started_at=datetime.now(timezone.utc))
    if row is not None:
        attempt = (row.attempts or 0) + 1
        _update_job(job_id, attempts=attempt)
    started = datetime.now(timezone.utc)
    error: str | None = None
    result: Any = None
    try:
        with tenant_scope(tenant_id):
            result = fn(*args, **kwargs)
        status = "completed"
    except Exception as exc:  # noqa: BLE001
        logger.exception("worker job %s (%s) raised", job_id, function_name)
        error = f"{type(exc).__name__}: {exc}"[:2000]
        status = "failed"
    finished = datetime.now(timezone.utc)
    excerpt = (str(result)[:500] if result is not None else None)
    _update_job(
        job_id, status=status, completed_at=finished,
        result_excerpt=excerpt, last_error=error,
    )
    _record_attempt(
        job_id=job_id, tenant_id=tenant_id, attempt_number=attempt,
        started=started, finished=finished, status=status, error=error,
    )
    if status == "failed":
        # Re-raise so RQ marks the underlying job as failed too.
        raise RuntimeError(error or "job failed")
    return result


# ---------------------------------------------------------------------------
# Query helpers used by the admin endpoints.
# ---------------------------------------------------------------------------

def get_job_status(job_id: str) -> dict | None:
    """Return ``{status, ...}`` for the Job row, or None if not found.

    Tenant-scoped via the auto-filter — callers in a tenant context only
    see their own jobs.
    """

    with SessionLocal() as db:
        row = db.get(Job, job_id)
        if not row:
            return None
        return {
            "id": row.id,
            "status": row.status,
            "function_name": row.function_name,
            "queue_name": row.queue_name,
            "attempts": row.attempts,
            "last_error": row.last_error,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "result_excerpt": row.result_excerpt,
            "rq_job_id": row.rq_job_id,
        }


def cancel_job(job_id: str) -> bool:
    """Best-effort cancel. Only meaningful for ``queued`` jobs; running
    jobs continue until they finish (RQ has no preemption)."""

    with SessionLocal() as db:
        row = db.get(Job, job_id)
        if not row:
            return False
        if row.status not in {"queued", "running"}:
            return False
        # If RQ-backed, also try to remove it from the queue. If that
        # fails (e.g. already started) we still flip the DB status so
        # the admin UI doesn't keep showing it as queued.
        rq_id = row.rq_job_id
        if rq_id:
            try:
                conn = _get_redis_connection()
                if conn is not None:
                    from rq.job import Job as RqJob  # type: ignore[import-not-found]

                    rj = RqJob.fetch(rq_id, connection=conn)
                    rj.cancel()
            except Exception:
                logger.exception("RQ cancel failed for %s", rq_id)
        row.status = "cancelled"
        row.completed_at = datetime.now(timezone.utc)
        db.commit()
        return True


def retry_job(job_id: str) -> JobHandle | None:
    """Re-enqueue a previously failed/cancelled job using its stored
    function name + args. Returns a fresh handle.

    Tenant scoping carries over from the original row.
    """

    with SessionLocal() as db:
        row = db.get(Job, job_id)
        if not row:
            return None
        if row.status not in {"failed", "cancelled", "completed"}:
            # Can't retry something still queued/running.
            return None
        function_name = row.function_name
        args_json = row.args_json or {"args": [], "kwargs": {}}
        tenant_id = row.tenant_id
        queue = row.queue_name
        created_by_id = row.created_by_id

    fn = _resolve_dotted(function_name)
    args = tuple(args_json.get("args") or [])
    kwargs = dict(args_json.get("kwargs") or {})
    # Run in the original tenant scope rather than the caller's so retries
    # of a Tenant-A job from a sysadmin context still land on Tenant A.
    return enqueue(
        fn, *args,
        tenant_id=tenant_id, queue=queue, created_by_id=created_by_id,
        **kwargs,
    )


def list_jobs(
    db: Session,
    *,
    status: str | None = None,
    function_name: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Job]:
    """Tenant-scoped listing — auto-filter clamps to the caller's tenant."""

    stmt = select(Job).order_by(Job.created_at.desc())
    if status:
        stmt = stmt.where(Job.status == status)
    if function_name:
        stmt = stmt.where(Job.function_name == function_name)
    stmt = stmt.offset(offset).limit(limit)
    return list(db.scalars(stmt).all())


def get_job_with_attempts(db: Session, job_id: str) -> tuple[Job | None, list[JobAttempt]]:
    """Return the Job + its ordered attempts, both tenant-scoped."""

    row = db.get(Job, job_id)
    if not row:
        return None, []
    attempts = list(db.scalars(
        select(JobAttempt)
        .where(JobAttempt.job_id == job_id)
        .order_by(JobAttempt.attempt_number.asc())
    ).all())
    return row, attempts


def get_stats(db: Session) -> dict:
    """Counters for the dashboard tile.

    ``completed_today``/``failed_today``/``cancelled_today`` are counted
    against UTC midnight of the current day for simplicity — callers that
    care about local-tz boundaries can re-bucket on the client.
    """

    midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    def _count(where) -> int:
        from sqlalchemy import func

        return db.scalar(select(func.count(Job.id)).where(where)) or 0

    return {
        "queued": _count(Job.status == "queued"),
        "running": _count(Job.status == "running"),
        "completed_today": _count(
            (Job.status == "completed") & (Job.completed_at >= midnight)
        ),
        "failed_today": _count(
            (Job.status == "failed") & (Job.completed_at >= midnight)
        ),
        "cancelled_today": _count(
            (Job.status == "cancelled") & (Job.completed_at >= midnight)
        ),
        "total": _count(Job.id.isnot(None)),
    }
