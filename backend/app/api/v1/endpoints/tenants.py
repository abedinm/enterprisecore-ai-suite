"""Tenants module — signup, current-tenant ops, user invites, usage."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Body, Depends, Request, Response, status
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.api.v1.endpoints.auth import _clear_auth_cookies, _issue_tokens, _set_auth_cookies
from app.core.config import settings as app_settings
from app.core.exceptions import (
    AppError, AuthenticationError, ConflictError, NotFoundError,
    PermissionDenied, ValidationFailed,
)
from app.core.security import hash_password
from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.db.base import Base
from app.db.session import get_db
from app.models.ai import AiUsageRecord
from app.models.tenant import Tenant, TenantInvite
from app.models.user import User, UserRole
from app.schemas.tenant import (
    TenantAcceptInvite, TenantDeleteIn, TenantDeleteReceipt, TenantInviteIn,
    TenantInviteOut, TenantRead, TenantSignup, TenantSignupResponse,
    TenantUpdate, TenantUsageOut,
)

router = APIRouter()

# Magic-link tokens live for 7 days so the invitee has plenty of time to
# accept while still being short enough to expire if leaked.
INVITE_TTL = timedelta(days=7)


# ---------------------------------------------------------------------------
# Signup — public, no auth.
# ---------------------------------------------------------------------------
@router.post(
    "/signup",
    response_model=TenantSignupResponse,
    status_code=status.HTTP_201_CREATED,
)
def signup(payload: TenantSignup, response: Response, db: Session = Depends(get_db)) -> TenantSignupResponse:
    """Create a new tenant + its first admin user, return an access token.

    Public endpoint: no auth required, no existing tenant context. The
    bypass_tenant_filter wrapper lets us look up "any tenant with this slug"
    across the whole table — outside a bypass, the auto-filter would only
    let us see rows of the current (unset) tenant.
    """
    slug = payload.slug.strip().lower()
    with bypass_tenant_filter():
        if db.scalar(select(Tenant).where(Tenant.slug == slug)):
            raise ConflictError(f"A tenant with slug '{slug}' already exists")

    contact_email = (payload.primary_contact_email or payload.admin_email).strip().lower()
    tenant = Tenant(
        name=payload.name.strip(),
        slug=slug,
        plan="evaluation",
        status="active",
        settings={},
        primary_contact_email=contact_email,
        timezone=payload.timezone or "UTC",
        currency=payload.currency or "USD",
    )
    # Bypass while we create the tenant (the auto-filter would otherwise
    # try to attach it to the current — unset — tenant).
    with bypass_tenant_filter():
        db.add(tenant)
        db.flush()

    # Create the first user *inside* the new tenant's scope so the auto-set
    # hook fills tenant_id correctly.
    admin_email = payload.admin_email.strip().lower()
    with tenant_scope(tenant.id):
        existing = db.scalar(select(User).where(User.email == admin_email))
        if existing:
            db.rollback()
            raise ConflictError("A user with this email already exists in the new tenant")
        user = User(
            email=admin_email,
            full_name=payload.admin_full_name,
            password_hash=hash_password(payload.admin_password),
            role=UserRole.admin,
            is_active=True,
        )
        db.add(user)
        db.flush()
        tokens = _issue_tokens(user, db)
        db.commit()
        db.refresh(tenant)
        db.refresh(user)

    _set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return TenantSignupResponse(
        tenant=TenantRead.model_validate(tenant),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


# ---------------------------------------------------------------------------
# Current-tenant ops — auth required.
# ---------------------------------------------------------------------------
@router.get("/me", response_model=TenantRead)
def get_my_tenant(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Tenant:
    tenant = db.get(Tenant, current_user.tenant_id)
    if not tenant:
        # Should be impossible — the auth dep guarantees the user has a
        # valid tenant — but check anyway so we never crash on a stale row.
        raise NotFoundError("Tenant not found")
    return tenant


@router.patch("/me", response_model=TenantRead)
def update_my_tenant(
    payload: TenantUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> Tenant:
    tenant = db.get(Tenant, current_user.tenant_id)
    if not tenant:
        raise NotFoundError("Tenant not found")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(tenant, field, value)
    db.commit()
    db.refresh(tenant)
    return tenant


# ---------------------------------------------------------------------------
# Inviting and accepting users.
# ---------------------------------------------------------------------------
@router.post(
    "/me/users/invite",
    response_model=TenantInviteOut,
    status_code=status.HTTP_201_CREATED,
)
def invite_user(
    payload: TenantInviteIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> TenantInviteOut:
    """Generate a magic-link invite. The token is returned once in the
    response so the caller (UI / API consumer) can email it out. Subsequent
    reads of the invite row omit the token."""
    email = payload.email.strip().lower()
    # Reject duplicate active invites for the same email + tenant.
    existing = db.scalar(
        select(TenantInvite).where(
            TenantInvite.tenant_id == current_user.tenant_id,
            TenantInvite.email == email,
            TenantInvite.status == "pending",
        )
    )
    if existing:
        raise ConflictError("An invite is already pending for this email")

    token = secrets.token_urlsafe(48)
    invite = TenantInvite(
        tenant_id=current_user.tenant_id,
        email=email,
        role=payload.role.value if hasattr(payload.role, "value") else str(payload.role),
        token=token,
        status="pending",
        invited_by_id=current_user.id,
        expires_at=datetime.now(timezone.utc) + INVITE_TTL,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    # Stand-in for real email delivery — log the magic link the inviter
    # would have received.
    logger.info(
        "Tenant invite created: tenant={} email={} accept_url=/api/v1/tenants/accept-invite?token={}",
        current_user.tenant_id, email, token,
    )
    out = TenantInviteOut.model_validate(invite)
    out.token = token
    return out


@router.post(
    "/accept-invite",
    response_model=TenantSignupResponse,
    status_code=status.HTTP_201_CREATED,
)
def accept_invite(
    payload: TenantAcceptInvite,
    response: Response,
    db: Session = Depends(get_db),
) -> TenantSignupResponse:
    """Public endpoint — the invited user redeems the magic link.

    Creates the User row under the target tenant and returns an access token
    so the new user is auto-logged-in.
    """
    with bypass_tenant_filter():
        invite = db.scalar(
            select(TenantInvite).where(TenantInvite.token == payload.token)
        )
    if not invite:
        raise NotFoundError("Invite not found")
    if invite.status != "pending":
        raise AppError("Invite is no longer active", code="invite_consumed", status_code=410)
    expires_at = invite.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        invite.status = "revoked"
        db.commit()
        raise AppError("Invite has expired", code="invite_expired", status_code=410)

    tenant_id = invite.tenant_id
    with tenant_scope(tenant_id):
        if db.scalar(select(User).where(User.email == invite.email)):
            raise ConflictError("A user with this email already exists in the target tenant")
        try:
            role = UserRole(invite.role)
        except ValueError:
            role = UserRole.employee
        user = User(
            email=invite.email,
            full_name=payload.full_name,
            password_hash=hash_password(payload.password),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.flush()
        invite.status = "accepted"
        tokens = _issue_tokens(user, db)
        db.commit()
        db.refresh(user)
        tenant = db.get(Tenant, tenant_id)

    _set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return TenantSignupResponse(
        tenant=TenantRead.model_validate(tenant),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


# ---------------------------------------------------------------------------
# Usage snapshot.
# ---------------------------------------------------------------------------
@router.get("/me/usage", response_model=TenantUsageOut)
def my_usage(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TenantUsageOut:
    """Return user count, storage usage, and YTD AI spend for the current
    tenant. Storage_mb walks every byte-bearing table for this tenant via
    :func:`app.services.tenant_usage.get_tenant_storage_mb` (5-min cache)."""
    from app.services.tenant_usage import get_tenant_storage_mb

    user_count = db.scalar(select(func.count(User.id))) or 0
    ytd_start = datetime(datetime.now(timezone.utc).year, 1, 1, tzinfo=timezone.utc)
    ai_spend = db.scalar(
        select(func.coalesce(func.sum(AiUsageRecord.cost_usd), Decimal("0"))).where(
            AiUsageRecord.occurred_at >= ytd_start
        )
    ) or Decimal("0")
    storage_mb = get_tenant_storage_mb(db, current_user.tenant_id)
    return TenantUsageOut(
        user_count=int(user_count),
        storage_mb=storage_mb,
        ai_spend_ytd_usd=float(ai_spend),
    )


# ---------------------------------------------------------------------------
# Destructive: delete the entire tenant. Admin + confirmation required.
# ---------------------------------------------------------------------------
DELETE_CONFIRMATION_STRING = "DELETE-MY-TENANT"


def _tables_with_tenant_id() -> list:
    """Every mapped table that carries a ``tenant_id`` column. Used for the
    deletion receipt — we count rows in each before the cascade removes them.
    The ``tenants`` table itself is excluded; we delete that last."""
    out = []
    for table in Base.metadata.sorted_tables:
        if "tenant_id" in table.c and table.name != "tenants":
            out.append(table)
    return out


def _write_deletion_receipt(receipt: TenantDeleteReceipt) -> Path:
    """Persist the receipt to ``storage/deletion-receipts/`` for compliance."""
    target_dir = app_settings.storage_dir / "deletion-receipts"
    target_dir.mkdir(parents=True, exist_ok=True)
    ts = receipt.deleted_at.strftime("%Y%m%dT%H%M%SZ")
    target = target_dir / f"{receipt.tenant_id}-{ts}.json"
    target.write_text(json.dumps(receipt.model_dump(mode="json"), indent=2, default=str), encoding="utf-8")
    return target


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_my_tenant(
    payload: TenantDeleteIn = Body(...),
    response: Response = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> Response:
    """Cascade-delete every record owned by the current tenant.

    Admin-only and gated behind an explicit confirmation string. The CASCADE
    FK chain established in migration 0013_multitenant means dropping the
    ``tenants`` row is enough to wipe every child table; we count rows first
    so the receipt enumerates exactly what got deleted.

    Side-effects:

    * Records an ``audit_logs`` row in the doomed tenant's own scope right
      before the cascade (the row will itself be cascaded a heartbeat later).
    * Writes a JSON receipt to ``storage/deletion-receipts/<tid>-<ts>.json``
      so the deletion is provable after the DB rows are gone.
    * Clears auth cookies on the response — best-effort logout.
    """
    if payload.confirmation != DELETE_CONFIRMATION_STRING:
        raise AppError(
            f"Confirmation string must be exactly {DELETE_CONFIRMATION_STRING!r}",
            code="bad_confirmation",
            status_code=400,
        )

    tenant_id = current_user.tenant_id
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise NotFoundError("Tenant not found")

    # Count rows per table before the cascade fires so the receipt is
    # informative. Bypass the tenant filter for the SELECTs because we're
    # about to delete the row that grounds the filter anyway.
    counts: dict[str, int] = {}
    with bypass_tenant_filter():
        for table in _tables_with_tenant_id():
            try:
                count = db.scalar(
                    select(func.count()).select_from(table).where(
                        table.c.tenant_id == tenant_id
                    )
                ) or 0
                if count:
                    counts[table.name] = int(count)
            except Exception:
                logger.exception("delete_my_tenant: count failed for table %s", table.name)

    receipt = TenantDeleteReceipt(
        tenant_id=tenant_id,
        tenant_slug=tenant.slug,
        tenant_name=tenant.name,
        requested_by_id=current_user.id,
        requested_by_email=current_user.email,
        reason=payload.reason,
        deleted_at=datetime.now(timezone.utc),
        deleted_record_counts=counts,
    )

    # Persist the receipt to disk BEFORE the cascade — if the DELETE fails
    # we'd rather have a stray receipt to investigate than a lost one.
    receipt_path = _write_deletion_receipt(receipt)
    logger.info(
        "delete_my_tenant: wrote receipt for tenant={} slug={} to {}",
        tenant_id, tenant.slug, receipt_path,
    )

    # Audit-log row in the doomed tenant's scope. It'll be cascaded with the
    # rest, but the receipt on disk preserves the audit trail.
    from app.services.audit import record_audit
    with tenant_scope(tenant_id):
        record_audit(
            db,
            actor=current_user,
            action="tenant.deleted",
            entity_type="tenant",
            entity_id=tenant_id,
            detail={
                "slug": tenant.slug,
                "name": tenant.name,
                "reason": payload.reason,
                "deleted_record_counts": counts,
            },
        )
        db.commit()

    # Now the cascade. The tenants table doesn't itself have a tenant_id
    # FK column, so we have to delete it manually (the cascade is FROM
    # tenants TO every child, not the other way around).
    with bypass_tenant_filter():
        db.delete(tenant)
        db.commit()

    # Invalidate the storage-MB cache for this tenant (best-effort — the
    # process may not see another request for this tid anyway).
    try:
        from app.services.tenant_usage import invalidate_cache
        invalidate_cache(tenant_id)
    except Exception:
        pass

    if response is not None:
        _clear_auth_cookies(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
