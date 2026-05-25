"""GDPR compliance endpoints.

  * ``POST /gdpr/export`` — kick off a data-export job. Returns ``{job_id}``.
  * ``GET /gdpr/export/{job_id}`` — poll status. When ``ready``, includes
    a signed download URL valid for 24h.
  * ``GET /gdpr/export/{job_id}/download`` — serves the signed file. The
    ``token`` query param must match the job's ``download_token``.
  * ``POST /gdpr/erasure-request`` (admin) — anonymizes a user.
  * ``GET /gdpr/erasure-receipts`` (admin) — returns the receipt audit trail.
  * ``GET /gdpr/data-categories`` — documentation feed for the privacy policy.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.cache import cache_response
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.webhooks import GdprErasureReceipt, GdprExportJob
from app.schemas.webhooks import (
    DataCategory, GdprErasureReceiptOut, GdprErasureRequest, GdprExportJobOut,
    GdprExportRequest,
)
from app.services.audit import record_audit
from app.services.event_bus import publish_event
from app.services.gdpr import DATA_CATEGORIES, erase_user, run_export_job

router = APIRouter()


EXPORT_DIR = Path("storage/exports")


def _job_to_out(job: GdprExportJob) -> dict:
    download_url = None
    if job.status == "ready" and job.download_token:
        download_url = f"/api/v1/gdpr/export/{job.id}/download?token={job.download_token}"
    return {
        "id": job.id,
        "user_id": job.user_id,
        "status": job.status,
        "download_url": download_url,
        "expires_at": job.expires_at,
        "completed_at": job.completed_at,
        "error_message": job.error_message,
        "record_count": job.record_count,
        "created_at": job.created_at,
    }


@router.get("/data-categories", response_model=list[DataCategory])
@cache_response(ttl=3600, namespace="gdpr:data-categories")
def data_categories(response: Response, _: User = Depends(get_current_user)):
    """Documentation of the categories of personal data the suite stores per
    user. Front-end privacy page reads from here so it can't drift from
    the underlying export behaviour."""

    return DATA_CATEGORIES


@router.post("/export", response_model=GdprExportJobOut, status_code=status.HTTP_202_ACCEPTED)
def request_export(
    payload: GdprExportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create + immediately run the export job.

    Non-admins can only export their OWN data. Admins can export any user
    in the same tenant. The tenant auto-filter prevents cross-tenant
    exports at the ORM layer either way.
    """

    target_id = payload.user_id or user.id
    if target_id != user.id and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Only admins may export another user's data")
    target = db.get(User, target_id)
    if target is None or target.tenant_id != user.tenant_id:
        raise NotFoundError("Target user not found")

    job = GdprExportJob(
        user_id=target.id,
        requested_by_id=user.id,
        status="running",
    )
    db.add(job)
    db.flush()
    record_audit(
        db, actor=user, action="export.request", entity_type="gdpr",
        entity_id=job.id, detail={"target_user_id": target.id},
    )
    db.commit()
    db.refresh(job)

    # Run synchronously for now — tasks list says "don't queue".
    run_export_job(db, job, EXPORT_DIR)
    db.refresh(job)
    return _job_to_out(job)


@router.get("/export/{job_id}", response_model=GdprExportJobOut)
def get_export(job_id: str, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    job = db.get(GdprExportJob, job_id)
    if not job:
        raise NotFoundError("Export job not found")
    if job.user_id != user.id and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Not authorised")
    return _job_to_out(job)


@router.get("/export/{job_id}/download")
def download_export(
    job_id: str,
    token: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Serve the export file. The token must match the job's
    ``download_token`` and the job must not have expired."""

    job = db.get(GdprExportJob, job_id)
    if not job or job.status != "ready":
        raise NotFoundError("Export not ready")
    if job.user_id != user.id and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Not authorised")
    if not job.download_token or token != job.download_token:
        raise HTTPException(status_code=403, detail="Invalid download token")
    if job.expires_at:
        exp = job.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Download link expired")
    if not job.download_path:
        raise NotFoundError("Export file missing")
    fpath = Path("storage") / job.download_path.replace("\\", "/")
    if not fpath.exists():
        raise NotFoundError("Export file missing on disk")
    return FileResponse(
        path=str(fpath),
        media_type="application/json",
        filename=f"export-{job.user_id}-{job.id}.json",
    )


@router.post(
    "/erasure-request",
    response_model=GdprErasureReceiptOut,
    status_code=status.HTTP_201_CREATED,
)
def erasure_request(
    payload: GdprErasureRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(UserRole.admin)),
):
    target = db.get(User, payload.user_id)
    if target is None or target.tenant_id != admin.tenant_id:
        raise NotFoundError("Target user not found")
    if target.id == admin.id:
        # Don't let an admin lock themselves out by erasing their own account
        # — they should hand off admin first, then have the new admin do it.
        raise HTTPException(
            status_code=400,
            detail="Admins cannot erase their own account; another admin must do it.",
        )

    receipt = erase_user(db, target, requested_by=admin, reason=payload.reason)
    record_audit(
        db, actor=admin, action="erasure", entity_type="user",
        entity_id=target.id, detail={"receipt_id": receipt.id, "reason": payload.reason},
    )
    publish_event(
        "user.deactivated",
        payload={"user_id": target.id, "reason": "gdpr_erasure"},
        user_id=admin.id,
    )
    db.commit()
    db.refresh(receipt)
    return receipt


@router.get("/erasure-receipts", response_model=list[GdprErasureReceiptOut])
def list_receipts(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    receipts = db.scalars(
        select(GdprErasureReceipt).order_by(GdprErasureReceipt.completed_at.desc())
    ).all()
    return receipts
