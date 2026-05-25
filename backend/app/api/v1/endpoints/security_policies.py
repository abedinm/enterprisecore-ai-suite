"""Tenant security policies — IP allowlist + audit stream destinations."""
from __future__ import annotations

import ipaddress
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.encryption import encrypt_field_for_current_tenant
from app.core.exceptions import NotFoundError, ValidationFailed
from app.core.tenant_context import get_current_tenant_id
from app.db.session import get_db
from app.models.security_hardening import (
    AuditStreamDestination, TenantSecurityPolicy,
)
from app.models.user import User, UserRole
from app.schemas.common import ORMModel

router = APIRouter()


# ---------- Security policy --------------------------------------------------
class SecurityPolicyOut(BaseModel):
    ip_allowlist_cidrs: list[str]
    ip_allowlist_enforced: bool


class IpAllowlistIn(BaseModel):
    cidrs: list[str] = Field(default_factory=list, max_length=200)
    enforced: bool = False

    @field_validator("cidrs")
    @classmethod
    def _validate_cidrs(cls, v: list[str]) -> list[str]:
        for cidr in v:
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError as exc:
                raise ValidationFailed(f"Invalid CIDR: {cidr}") from exc
        return v


def _get_or_create_policy(db: Session, tenant_id: str) -> TenantSecurityPolicy:
    policy = db.scalar(
        select(TenantSecurityPolicy).where(TenantSecurityPolicy.tenant_id == tenant_id)
    )
    if not policy:
        policy = TenantSecurityPolicy(
            ip_allowlist_cidrs=[],
            ip_allowlist_enforced=False,
        )
        db.add(policy)
        db.commit()
        db.refresh(policy)
    return policy


@router.get("/policies", response_model=SecurityPolicyOut)
def get_policy(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    tid = get_current_tenant_id()
    policy = _get_or_create_policy(db, tid)
    return SecurityPolicyOut(
        ip_allowlist_cidrs=policy.ip_allowlist_cidrs or [],
        ip_allowlist_enforced=policy.ip_allowlist_enforced,
    )


@router.put("/policies/ip-allowlist", response_model=SecurityPolicyOut)
def update_ip_allowlist(
    payload: IpAllowlistIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    tid = get_current_tenant_id()
    policy = _get_or_create_policy(db, tid)
    policy.ip_allowlist_cidrs = payload.cidrs
    policy.ip_allowlist_enforced = payload.enforced
    db.commit()
    db.refresh(policy)
    return SecurityPolicyOut(
        ip_allowlist_cidrs=policy.ip_allowlist_cidrs or [],
        ip_allowlist_enforced=policy.ip_allowlist_enforced,
    )


# ---------- Audit stream destinations ---------------------------------------
class AuditStreamIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    destination_type: str = Field(pattern=r"^(webhook|splunk_hec|datadog_logs|sumo_logic)$")
    url: str = Field(min_length=1)
    credentials: str | None = Field(default=None, description="HEC token / API key / bearer")
    is_active: bool = True


class AuditStreamUpdate(BaseModel):
    name: str | None = None
    destination_type: str | None = Field(default=None, pattern=r"^(webhook|splunk_hec|datadog_logs|sumo_logic)$")
    url: str | None = None
    credentials: str | None = None
    is_active: bool | None = None


class AuditStreamOut(ORMModel):
    id: str
    name: str
    destination_type: str
    url: str
    is_active: bool
    last_success_at: datetime | None
    last_error_at: datetime | None
    last_error_message: str | None
    consecutive_failures: int
    created_at: datetime
    updated_at: datetime


@router.get("/audit-stream-destinations", response_model=list[AuditStreamOut])
def list_destinations(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    return db.scalars(
        select(AuditStreamDestination).order_by(AuditStreamDestination.created_at.desc())
    ).all()


@router.post("/audit-stream-destinations", response_model=AuditStreamOut, status_code=201)
def create_destination(
    payload: AuditStreamIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    dest = AuditStreamDestination(
        name=payload.name,
        destination_type=payload.destination_type,
        url=payload.url,
        credentials_encrypted=(
            encrypt_field_for_current_tenant(payload.credentials)
            if payload.credentials else None
        ),
        is_active=payload.is_active,
    )
    db.add(dest)
    db.commit()
    db.refresh(dest)
    return dest


@router.patch("/audit-stream-destinations/{dest_id}", response_model=AuditStreamOut)
def update_destination(
    dest_id: str,
    payload: AuditStreamUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    dest = db.get(AuditStreamDestination, dest_id)
    if not dest:
        raise NotFoundError("Audit stream destination not found")
    if payload.name is not None:
        dest.name = payload.name
    if payload.destination_type is not None:
        dest.destination_type = payload.destination_type
    if payload.url is not None:
        dest.url = payload.url
    if payload.credentials is not None:
        dest.credentials_encrypted = encrypt_field_for_current_tenant(payload.credentials)
    if payload.is_active is not None:
        dest.is_active = payload.is_active
    db.commit()
    db.refresh(dest)
    return dest


@router.delete("/audit-stream-destinations/{dest_id}", status_code=204)
def delete_destination(
    dest_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    dest = db.get(AuditStreamDestination, dest_id)
    if not dest:
        raise NotFoundError("Audit stream destination not found")
    db.delete(dest)
    db.commit()
    return None


@router.post("/audit-stream-destinations/{dest_id}/test")
def test_destination(
    dest_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    """POST a single canary event so the operator can confirm
    connectivity. Records success/failure on the destination row."""
    dest = db.get(AuditStreamDestination, dest_id)
    if not dest:
        raise NotFoundError("Audit stream destination not found")
    from app.services.audit_streamer import test_destination as _test
    ok, error = _test(dest, db)
    return {"ok": ok, "error": error}
