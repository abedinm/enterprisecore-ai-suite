"""Magic-link authentication endpoints.

Three purposes share the same plumbing:

* ``login`` — passwordless sign-in. Token consumption sets auth cookies +
  returns the JWT pair.
* ``password_reset`` — token consumption returns a short-lived
  ``reset_token`` that the caller POSTs to a separate confirm endpoint
  (out of scope here — owned by the auth module).
* ``email_verification`` — same as login but the consume step also
  marks the user as verified (not modelled yet — placeholder for
  future ``email_verified_at`` column).

Two layers of anti-abuse:

* Per-email rate limit (5/hour) on issuance — see the dependency on
  ``RateLimit``.
* "No enumeration": the response is always ``{ok: true}`` regardless of
  whether the email actually exists. That prevents the endpoint being
  used as an account-discovery oracle.
"""
# NB: no `from __future__ import annotations` per the FastAPI signature
# introspection rule documented in auth.py.
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import _issue_tokens, _set_auth_cookies
from app.core.exceptions import AppError, AuthenticationError
from app.core.rate_limit import RateLimit
from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.db.session import get_db
from app.models.sso import MagicLinkToken
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.sso import MagicLinkConsume, MagicLinkConsumeResponse, MagicLinkRequest
from app.services.email import send_email

router = APIRouter()

MAGIC_LINK_TTL = timedelta(minutes=15)
RESET_TOKEN_TTL = timedelta(minutes=15)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _public_base_url(request: Request) -> str:
    """Pick the base URL the SPA is served at.

    Configured ``APP_BASE_URL`` env var wins (production deploys must set
    it). Falls back to the request's host header so local dev keeps
    working without configuration.
    """
    from app.core.config import settings as _settings

    configured = (_settings.app_base_url or "").strip().rstrip("/")
    if configured:
        return configured
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "localhost"
    return f"{proto}://{host}"


def _build_consume_url(base_url: str, raw_token: str) -> str:
    """Render a magic-link URL that the frontend's HashRouter can route.

    The SPA lives behind ``#/auth/consume?token=...`` (HashRouter — the
    hash is preserved by the browser through redirects and not sent to
    the server). The previous version of this code pointed straight at
    the JSON API endpoint, which produced raw JSON in the browser when a
    user clicked the email link.
    """
    return f"{base_url.rstrip('/')}/#/auth/consume?token={raw_token}"


@router.post(
    "/magic-link",
    status_code=status.HTTP_200_OK,
    # Aggressive rate limit — at most 5 issuances per minute from one IP,
    # and we additionally key by email below.
    dependencies=[Depends(RateLimit("30/hour", id="magic-link-issue"))],
)
def issue_magic_link(
    payload: MagicLinkRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a magic-link token and email it.

    Always returns ``{ok: true}`` — even if the email doesn't exist —
    so attackers can't enumerate registered emails through this endpoint.
    """
    email = payload.email.strip().lower()
    purpose = payload.purpose

    # Resolve the tenant. ``tenant_slug`` is required for login/email_verification
    # (which need a tenant context to find the user) but optional for password
    # reset (which intentionally looks across tenants by email).
    tenant: Tenant | None = None
    if payload.tenant_slug:
        with bypass_tenant_filter():
            tenant = db.scalar(select(Tenant).where(Tenant.slug == payload.tenant_slug.strip().lower()))
    # ----- Per-email rate limit -----------------------------------------
    # 5 active (non-used, non-expired) tokens per email at most. If the
    # caller is burning through them faster than that we treat the burst
    # as abuse and return the same {ok: true} without issuing.
    with bypass_tenant_filter():
        recent_count = db.scalar(
            select(func_count()).select_from(MagicLinkToken).where(
                MagicLinkToken.email == email,
                MagicLinkToken.purpose == purpose,
                MagicLinkToken.created_at > datetime.now(timezone.utc) - timedelta(hours=1),
            )
        ) or 0
    if recent_count >= 5:
        return {"ok": True}

    # ----- Look up user (no enumeration) --------------------------------
    user: User | None = None
    if tenant:
        with tenant_scope(tenant.id):
            user = db.scalar(select(User).where(User.email == email))
    else:
        with bypass_tenant_filter():
            user = db.scalar(select(User).where(User.email == email))

    # If the email/tenant combo doesn't resolve to an active user we still
    # respond OK — but never email anyone.
    if not user or not user.is_active:
        return {"ok": True}

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    with bypass_tenant_filter():
        db.add(
            MagicLinkToken(
                tenant_id=tenant.id if tenant else (user.tenant_id if purpose != "password_reset" else None),
                email=email,
                purpose=purpose,
                token_hash=token_hash,
                expires_at=datetime.now(timezone.utc) + MAGIC_LINK_TTL,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        )
        db.commit()

    base_url = _public_base_url(request)
    link = _build_consume_url(base_url, raw_token)
    subject_map = {
        "login": "Your sign-in link",
        "password_reset": "Reset your password",
        "email_verification": "Verify your email",
    }
    body = (
        f"Hello,\n\n"
        f"Use the link below to {purpose.replace('_', ' ')}. It expires in 15 minutes.\n\n"
        f"{link}\n\n"
        f"If you didn't request this, you can ignore the message."
    )
    send_email(
        to=email,
        subject=subject_map.get(purpose, "Your sign-in link"),
        body_text=body,
    )
    return {"ok": True}


@router.post(
    "/magic-link/consume",
    response_model=MagicLinkConsumeResponse,
    dependencies=[Depends(RateLimit("60/minute", id="magic-link-consume"))],
)
def consume_magic_link(
    payload: MagicLinkConsume,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> MagicLinkConsumeResponse:
    """Redeem a magic-link token. Single-use — the row is stamped
    ``used_at`` on success so a replay is rejected by the second branch
    below."""
    token_hash = _hash_token(payload.token)
    with bypass_tenant_filter():
        row = db.scalar(select(MagicLinkToken).where(MagicLinkToken.token_hash == token_hash))
    if not row:
        raise AuthenticationError("Invalid magic-link token")
    if row.used_at is not None:
        raise AuthenticationError("Magic-link token has already been used")
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise AuthenticationError("Magic-link token has expired")

    # Find the target user. For password reset the tenant_id may be NULL
    # — look the user up by email globally (bypassing the filter).
    user: User | None = None
    if row.tenant_id:
        with tenant_scope(row.tenant_id):
            user = db.scalar(select(User).where(User.email == row.email))
    else:
        with bypass_tenant_filter():
            user = db.scalar(select(User).where(User.email == row.email))
    if not user or not user.is_active:
        raise AuthenticationError("User account is no longer active")

    row.used_at = datetime.now(timezone.utc)
    if row.purpose == "password_reset":
        # Issue a short-lived reset token bound to the user. The caller
        # posts it to /auth/password-reset/confirm — out of scope here.
        from app.core.security import create_access_token

        # We reuse the access-token JWT machinery with a custom claim
        # to keep the surface area small. The confirm endpoint validates
        # the type=password_reset claim before flipping the password.
        reset_token = create_access_token(
            subject=user.id, role="password_reset",
            expires_delta=RESET_TOKEN_TTL,
        )
        db.commit()
        return MagicLinkConsumeResponse(
            purpose=row.purpose,
            reset_token=reset_token,
            email=user.email,
        )

    # login / email_verification — issue access + refresh, set cookies.
    with tenant_scope(user.tenant_id):
        user.last_login_at = datetime.now(timezone.utc)
        tokens = _issue_tokens(user, db)
        db.commit()
    _set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return MagicLinkConsumeResponse(
        purpose=row.purpose,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        email=user.email,
    )


# ---------------------------------------------------------------------------
# Tiny helper — SQLAlchemy 2.x's ``func.count`` is the canonical way to
# count rows in a select, but importing it locally keeps the top of the
# file tidy. ``func_count`` returns the same expression.
# ---------------------------------------------------------------------------
def func_count():  # pragma: no cover  — trivial helper
    from sqlalchemy import func
    return func.count()
