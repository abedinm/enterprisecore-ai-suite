"""BYOK encryption admin endpoints — admin-only."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.encryption import (
    ensure_tenant_dek, rotate_tenant_dek, switch_to_byok,
)
from app.core.tenant_context import get_current_tenant_id
from app.db.session import get_db
from app.models.security_hardening import TenantEncryptionKey
from app.models.user import User, UserRole

router = APIRouter()


class EncryptionKeyOut(BaseModel):
    key_version: int
    kms_provider: str
    kms_key_ref: str | None
    is_active: bool
    activated_at: datetime
    rotated_at: datetime | None


class RotateOut(BaseModel):
    job_id: str
    new_key_version: int


class ByokIn(BaseModel):
    kms_provider: str = Field(pattern=r"^(server|aws_kms|gcp_kms|azure_kv|hcv_transit)$")
    kms_key_ref: str = Field(min_length=1, max_length=500)


@router.get("/key", response_model=EncryptionKeyOut)
def current_key(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    tid = get_current_tenant_id()
    row = ensure_tenant_dek(tid, db) if tid else None
    if not row:
        raise RuntimeError("No tenant context for encryption key lookup")
    return row


@router.get("/keys", response_model=list[EncryptionKeyOut])
def list_keys(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    """List every DEK row this tenant has had (history of rotations)."""
    rows = db.scalars(
        select(TenantEncryptionKey).order_by(TenantEncryptionKey.key_version.desc())
    ).all()
    return rows


@router.post("/rotate", response_model=RotateOut)
def rotate_key(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    tid = get_current_tenant_id()
    new_row = rotate_tenant_dek(tid, db) if tid else None
    if not new_row:
        raise RuntimeError("No tenant context for key rotation")
    # The actual re-encryption sweep is a background job — in this
    # implementation we kick it inline (cheap on a small DB). The job_id
    # is returned for API symmetry; today it's just the new key version.
    return RotateOut(job_id=f"rotate-{new_row.id}", new_key_version=new_row.key_version)


@router.post("/byok", response_model=EncryptionKeyOut)
def configure_byok(
    payload: ByokIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    tid = get_current_tenant_id()
    new_row = switch_to_byok(
        tenant_id=tid,
        kms_provider=payload.kms_provider,
        kms_key_ref=payload.kms_key_ref,
        db=db,
    ) if tid else None
    if not new_row:
        raise RuntimeError("No tenant context for BYOK switch")
    return new_row
