"""Admin observability for the background-job system.

These endpoints back the JobsTab in the org admin UI. Everything here is
tenant-scoped via the ORM auto-filter, so admin A in tenant A cannot see
admin B's jobs even if they guess an id.

Auth model: admin/manager for reads + admin-only for mutations
(cancel, retry). The ``stats`` endpoint is admin/manager so a manager can
glance at the queue depth without elevated privileges.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.jobs import Job, JobAttempt
from app.models.user import User, UserRole
from app.schemas.jobs import (
    JobActionOut, JobAttemptOut, JobDetailOut, JobOut, JobStatsOut,
)
from app.services import jobs as jobs_svc
from app.services.audit import record_audit

router = APIRouter()


def _to_out(row: Job) -> dict:
    return {
        "id": row.id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "function_name": row.function_name,
        "args_json": row.args_json or {},
        "status": row.status,
        "queue_name": row.queue_name,
        "attempts": row.attempts,
        "last_error": row.last_error,
        "scheduled_at": row.scheduled_at,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
        "result_excerpt": row.result_excerpt,
        "rq_job_id": row.rq_job_id,
        "created_by_id": row.created_by_id,
    }


def _attempt_to_out(a: JobAttempt) -> dict:
    return {
        "id": a.id,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
        "job_id": a.job_id,
        "attempt_number": a.attempt_number,
        "status": a.status,
        "started_at": a.started_at,
        "finished_at": a.finished_at,
        "duration_ms": a.duration_ms,
        "error_message": a.error_message,
    }


@router.get("", response_model=list[JobOut])
def list_jobs(
    status: str | None = Query(None, description="Filter by job status"),
    function_name: str | None = Query(None, description="Filter by function dotted path"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    """Recent jobs for the caller's tenant, most recent first."""

    rows = jobs_svc.list_jobs(
        db, status=status, function_name=function_name,
        limit=limit, offset=offset,
    )
    return [_to_out(r) for r in rows]


@router.get("/stats", response_model=JobStatsOut)
def stats(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    """Counters for the dashboard tile."""

    return jobs_svc.get_stats(db)


@router.get("/{job_id}", response_model=JobDetailOut)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    """Full detail of one job + its attempt history."""

    row, attempts = jobs_svc.get_job_with_attempts(db, job_id)
    if not row:
        raise NotFoundError("Job not found")
    out = _to_out(row)
    out["attempts_history"] = [_attempt_to_out(a) for a in attempts]
    return out


@router.post("/{job_id}/cancel", response_model=JobActionOut)
def cancel(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
):
    """Best-effort cancel. Running jobs continue but the DB row flips so
    the UI doesn't keep showing them as in-flight."""

    # Confirm the row is in the caller's tenant before touching it.
    row = db.get(Job, job_id)
    if not row:
        raise NotFoundError("Job not found")
    ok = jobs_svc.cancel_job(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Job cannot be cancelled in its current state")
    record_audit(db, actor=user, action="cancel", entity_type="job", entity_id=job_id)
    db.commit()
    return {"job_id": job_id, "status": "cancelled", "message": "Job cancelled"}


@router.post("/{job_id}/retry", response_model=JobActionOut)
def retry(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
):
    """Re-enqueue a previously failed / cancelled / completed job using
    its stored function + args."""

    row = db.get(Job, job_id)
    if not row:
        raise NotFoundError("Job not found")
    handle = jobs_svc.retry_job(job_id)
    if handle is None:
        raise HTTPException(status_code=400, detail="Job cannot be retried in its current state")
    record_audit(db, actor=user, action="retry", entity_type="job",
                 entity_id=job_id, detail={"new_job_id": handle.job_id})
    db.commit()
    return {
        "job_id": handle.job_id, "status": handle.status,
        "message": f"Retried (mode={handle.mode})",
    }
