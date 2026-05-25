"""WebAuthn passkey endpoints.

Surface for phishing-resistant 2FA / passwordless login:

* ``POST /webauthn/register/begin``  — auth-required. Returns the
  PublicKeyCredentialCreationOptions the browser passes to
  ``navigator.credentials.create({publicKey})``.
* ``POST /webauthn/register/finish`` — auth-required. Verifies the
  attestation, persists a :class:`WebAuthnCredential`.
* ``POST /webauthn/authenticate/begin``  — public. Body: ``{email}``.
  Returns PublicKeyCredentialRequestOptions. Always returns options
  even for unknown emails so the endpoint can't be used as an
  account-enumeration oracle.
* ``POST /webauthn/authenticate/finish`` — public. Verifies the
  assertion, mints an access+refresh pair, sets cookies, returns the
  same TokenResponse the password-login endpoint produces.
* ``GET    /webauthn/credentials``        — list mine.
* ``DELETE /webauthn/credentials/{id}``   — revoke mine.

Tenant model
============
Credentials are tenant-scoped. ``authenticate/begin`` runs without
auth, so it has to resolve the tenant from the supplied email before
the lookup — we scan across tenants for the email match, then scope
the rest of the ceremony to that user's tenant.
"""
# NB: no ``from __future__ import annotations`` so FastAPI's signature
# introspection sees concrete types (same reason auth.py opts out).
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.auth import _issue_tokens, _set_auth_cookies
from app.core.exceptions import AuthenticationError, NotFoundError
from app.core.rate_limit import RateLimit
from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.db.session import get_db
from app.models.user import User
from app.models.webauthn import WebAuthnCredential
from app.schemas.auth import TokenResponse
from app.schemas.webauthn import (
    AuthenticateBeginIn,
    AuthenticateBeginOut,
    AuthenticateFinishIn,
    CredentialListOut,
    CredentialSummary,
    RegisterBeginOut,
    RegisterFinishIn,
    RegisterFinishOut,
)
from app.services import webauthn as webauthn_svc
from app.services.audit import record_audit


router = APIRouter()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
@router.post(
    "/register/begin",
    response_model=RegisterBeginOut,
    dependencies=[Depends(RateLimit("30/minute", id="webauthn-register-begin"))],
)
def register_begin(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    options = webauthn_svc.generate_registration_options(db, user)
    db.commit()
    return RegisterBeginOut(publicKey=_coerce_options(options))


@router.post(
    "/register/finish",
    response_model=RegisterFinishOut,
    dependencies=[Depends(RateLimit("30/minute", id="webauthn-register-finish"))],
)
def register_finish(
    payload: RegisterFinishIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cred = webauthn_svc.verify_registration(
        db, user, payload.credential, nickname=payload.nickname
    )
    record_audit(
        db, actor=user, action="webauthn_register",
        entity_type="webauthn_credential", entity_id=cred.id,
        detail={"nickname": payload.nickname},
    )
    db.commit()
    db.refresh(cred)
    return RegisterFinishOut(
        id=cred.id, nickname=cred.nickname, created_at=cred.created_at,
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
@router.post(
    "/authenticate/begin",
    response_model=AuthenticateBeginOut,
    dependencies=[Depends(RateLimit("30/minute", id="webauthn-auth-begin"))],
)
def authenticate_begin(
    payload: AuthenticateBeginIn,
    db: Session = Depends(get_db),
):
    """Start a passkey authentication ceremony.

    Public endpoint. We don't reveal whether the email exists — the
    response shape is identical for known and unknown users (just an
    empty ``allowCredentials`` list when unknown). The server-side
    challenge row is still stored so the matching finish call has
    something to compare against.
    """
    email = str(payload.email).strip().lower()
    with bypass_tenant_filter():
        user = db.scalar(select(User).where(User.email == email))
    if user:
        with tenant_scope(user.tenant_id):
            options = webauthn_svc.generate_authentication_options(db, email)
            db.commit()
    else:
        # Stash the challenge under the *default* tenant so the schema
        # constraints are satisfied. The finish call will then look up
        # the email cross-tenant and fail to find a matching credential.
        from app.models.tenant import Tenant
        with bypass_tenant_filter():
            default = db.scalar(select(Tenant).where(Tenant.slug == "default"))
        target_tid = default.id if default else None
        with tenant_scope(target_tid):
            options = webauthn_svc.generate_authentication_options(db, email)
            db.commit()
    return AuthenticateBeginOut(publicKey=_coerce_options(options))


@router.post(
    "/authenticate/finish",
    response_model=TokenResponse,
    dependencies=[Depends(RateLimit("20/minute", id="webauthn-auth-finish"))],
)
def authenticate_finish(
    payload: AuthenticateFinishIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    email = str(payload.email).strip().lower()
    with bypass_tenant_filter():
        user = db.scalar(select(User).where(User.email == email))
    if not user or not user.is_active:
        raise AuthenticationError("Invalid passkey")
    with tenant_scope(user.tenant_id):
        try:
            verified_user, cred = webauthn_svc.verify_authentication(
                db, email, payload.credential
            )
        except AuthenticationError:
            db.rollback()
            raise
        # Cross-tenant defense: a credential lookup that comes back with
        # a user from a different tenant means somebody's trying to
        # log into tenant B with a tenant-A passkey.
        if verified_user.tenant_id != user.tenant_id:
            raise AuthenticationError("Invalid passkey")
        verified_user.last_login_at = datetime.now(timezone.utc)
        tokens = _issue_tokens(verified_user, db)
        record_audit(
            db, actor=verified_user, action="webauthn_login",
            entity_type="user", entity_id=verified_user.id,
            detail={"credential_id": cred.id},
        )
        db.commit()
        _set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
        return tokens


# ---------------------------------------------------------------------------
# Credential management
# ---------------------------------------------------------------------------
@router.get("/credentials", response_model=CredentialListOut)
def list_credentials(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = list(db.scalars(
        select(WebAuthnCredential)
        .where(WebAuthnCredential.user_id == user.id)
        .order_by(WebAuthnCredential.created_at.desc())
    ))
    return CredentialListOut(
        credentials=[CredentialSummary.model_validate(r) for r in rows]
    )


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_credential(
    credential_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cred = db.get(WebAuthnCredential, credential_id)
    if not cred or cred.user_id != user.id:
        raise NotFoundError("Credential not found")
    db.delete(cred)
    record_audit(
        db, actor=user, action="webauthn_revoke",
        entity_type="webauthn_credential", entity_id=credential_id,
        detail={},
    )
    db.commit()
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _coerce_options(options: Any) -> dict[str, Any]:
    """Normalise whatever ``options_to_json`` returned into a plain dict.

    The webauthn lib's ``options_to_json`` returns a JSON-encoded *str*;
    callers in tests may instead pass an already-decoded dict. Either is
    accepted here so we can serve the FastAPI response uniformly.
    """
    if isinstance(options, dict):
        return options
    if isinstance(options, (bytes, bytearray)):
        options = options.decode()
    if isinstance(options, str):
        import json
        try:
            return json.loads(options)
        except Exception:  # pragma: no cover
            return {"raw": options}
    return {"raw": str(options)}
