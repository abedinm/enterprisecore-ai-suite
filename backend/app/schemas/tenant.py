"""Pydantic schemas for the tenants module."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole
from app.schemas.common import ORMModel


class TenantSignup(BaseModel):
    """Public payload used by ``POST /tenants/signup`` — creates both the
    new tenant row and its first admin user atomically."""

    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    admin_email: str = Field(min_length=3, max_length=255)
    admin_password: str = Field(min_length=10, max_length=128)
    admin_full_name: str = Field(min_length=2, max_length=160)
    primary_contact_email: str | None = Field(default=None, max_length=255)
    timezone: str | None = Field(default="UTC", max_length=60)
    currency: str | None = Field(default="USD", min_length=3, max_length=3)


class TenantRead(ORMModel):
    id: str
    name: str
    slug: str
    plan: str
    status: str
    trial_ends_at: datetime | None = None
    primary_contact_email: str
    timezone: str
    currency: str
    settings: dict = {}
    created_at: datetime
    updated_at: datetime


class TenantUpdate(BaseModel):
    """Fields a tenant admin can change on their own tenant."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    primary_contact_email: str | None = Field(default=None, max_length=255)
    timezone: str | None = Field(default=None, max_length=60)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    settings: dict | None = None


class TenantInviteIn(BaseModel):
    """Body of ``POST /tenants/me/users/invite``."""

    email: str = Field(min_length=3, max_length=255)
    role: UserRole = UserRole.employee


class TenantInviteOut(ORMModel):
    id: str
    email: str
    role: str
    status: str
    expires_at: datetime
    # The magic-link token is returned exactly once on creation so the caller
    # can email it to the invitee. Subsequent reads omit it for security.
    token: str | None = None


class TenantAcceptInvite(BaseModel):
    """Body of ``POST /tenants/accept-invite``."""

    token: str = Field(min_length=10, max_length=80)
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=160)


class TenantSignupResponse(BaseModel):
    tenant: TenantRead
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TenantUsageOut(BaseModel):
    """Snapshot of resource usage for the current tenant — surfaced in the
    admin dashboard so users can see how close they are to plan limits."""

    user_count: int
    storage_mb: float
    ai_spend_ytd_usd: float


class TenantDeleteIn(BaseModel):
    """Body of ``DELETE /tenants/me`` — destructive, admin-only.

    The literal string ``DELETE-MY-TENANT`` must be supplied verbatim so a
    misclick / malformed UI payload cannot trigger the cascade. The optional
    ``reason`` is recorded in the deletion receipt for compliance audit.
    """

    confirmation: str = Field(min_length=1, max_length=64)
    reason: str | None = Field(default=None, max_length=500)


class TenantDeleteReceipt(BaseModel):
    """Returned to the caller in the deletion audit-log record AND written to
    ``storage/deletion-receipts/<tenant_id>-<timestamp>.json`` for compliance.
    """

    tenant_id: str
    tenant_slug: str
    tenant_name: str
    requested_by_id: str | None
    requested_by_email: str | None
    reason: str | None
    deleted_at: datetime
    deleted_record_counts: dict[str, int]
