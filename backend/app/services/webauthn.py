"""WebAuthn passkey registration + authentication ceremonies.

Thin wrapper around the canonical ``webauthn`` PyPI package that holds
the request/response state EnterpriseCore needs in the middle:

* generate registration / authentication options (challenge bytes,
  RP info, allowCredentials list)
* persist the per-ceremony challenge in :class:`WebAuthnChallenge`
* verify the browser's response and either create a new
  :class:`WebAuthnCredential` (registration) or bump ``sign_count`` +
  ``last_used_at`` (authentication)

Configuration
=============
Relying Party identity is configurable via env (``WEBAUTHN_RP_ID``,
``WEBAUTHN_RP_NAME``, ``WEBAUTHN_ORIGIN``) — the customer points these
at their actual hostname before going to production. The defaults match
the local-dev hostnames we ship.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, ValidationFailed
from app.models.user import User
from app.models.webauthn import WebAuthnChallenge, WebAuthnCredential


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_RP_ID = "enterprisecore.local"
DEFAULT_RP_NAME = "EnterpriseCore"
DEFAULT_ORIGIN = "https://app.enterprisecore.local"

# Challenges live this long before being rejected as stale. The W3C
# recommendation is "a few minutes" — 5 is conservative.
CHALLENGE_TTL = timedelta(minutes=5)


def rp_id() -> str:
    return os.environ.get("WEBAUTHN_RP_ID") or DEFAULT_RP_ID


def rp_name() -> str:
    return os.environ.get("WEBAUTHN_RP_NAME") or DEFAULT_RP_NAME


def origin() -> str:
    return os.environ.get("WEBAUTHN_ORIGIN") or DEFAULT_ORIGIN


# ---------------------------------------------------------------------------
# Lib loader
# ---------------------------------------------------------------------------
def _load_webauthn():
    """Import the optional ``webauthn`` package.

    Kept lazy because the test suite mocks individual symbols on this
    module before the lib would otherwise be touched. The lib is not
    bundled into the desktop .exe in the small-install SKU.
    """
    try:
        import webauthn  # type: ignore
        from webauthn.helpers.structs import (  # type: ignore  # noqa: F401
            AuthenticatorSelectionCriteria,
            PublicKeyCredentialDescriptor,
            UserVerificationRequirement,
        )
        return webauthn
    except Exception as exc:  # pragma: no cover - exercised in tests via mocks
        raise ValidationFailed(
            "The 'webauthn' package is not installed on the server. "
            "Install requirements.txt to enable passkey support."
        ) from exc


# ---------------------------------------------------------------------------
# Challenge persistence
# ---------------------------------------------------------------------------
def _new_challenge_bytes() -> bytes:
    # 32 random bytes; matches the lib's default and the spec's minimum.
    return secrets.token_bytes(32)


def _store_challenge(
    db: Session,
    *,
    purpose: str,
    challenge: bytes,
    user_id: str | None = None,
    email: str | None = None,
) -> WebAuthnChallenge:
    row = WebAuthnChallenge(
        user_id=user_id,
        email=email.lower() if email else None,
        purpose=purpose,
        challenge=challenge,
        expires_at=datetime.now(timezone.utc) + CHALLENGE_TTL,
    )
    db.add(row)
    db.flush()
    return row


def _find_latest_challenge(
    db: Session,
    *,
    purpose: str,
    user_id: str | None = None,
    email: str | None = None,
) -> WebAuthnChallenge:
    stmt = (
        select(WebAuthnChallenge)
        .where(WebAuthnChallenge.purpose == purpose)
        .where(WebAuthnChallenge.consumed_at.is_(None))
        .order_by(WebAuthnChallenge.created_at.desc())
    )
    if user_id:
        stmt = stmt.where(WebAuthnChallenge.user_id == user_id)
    if email:
        stmt = stmt.where(WebAuthnChallenge.email == email.lower())
    row = db.scalar(stmt)
    if not row:
        raise AuthenticationError("No matching WebAuthn challenge")
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise AuthenticationError("WebAuthn challenge has expired")
    return row


# ---------------------------------------------------------------------------
# Registration ceremony
# ---------------------------------------------------------------------------
def generate_registration_options(db: Session, user: User) -> dict[str, Any]:
    """Build PublicKeyCredentialCreationOptions for ``user`` + persist challenge."""
    webauthn = _load_webauthn()
    # Existing credentials this user already has — passed as
    # excludeCredentials so the authenticator doesn't register the same
    # key twice (the spec calls this credential collision).
    existing = list(db.scalars(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
    ))
    exclude = [
        webauthn.helpers.structs.PublicKeyCredentialDescriptor(id=c.credential_id)
        for c in existing
    ]

    options = webauthn.generate_registration_options(
        rp_id=rp_id(),
        rp_name=rp_name(),
        user_id=user.id.encode(),
        user_name=user.email,
        user_display_name=user.full_name or user.email,
        exclude_credentials=exclude,
    )
    # Persist the challenge so register/finish can verify.
    _store_challenge(db, purpose="register", challenge=options.challenge, user_id=user.id)
    return webauthn.options_to_json(options)


def verify_registration(
    db: Session,
    user: User,
    response: dict[str, Any],
    *,
    nickname: str | None = None,
) -> WebAuthnCredential:
    webauthn = _load_webauthn()
    challenge_row = _find_latest_challenge(db, purpose="register", user_id=user.id)
    try:
        verification = webauthn.verify_registration_response(
            credential=response,
            expected_challenge=challenge_row.challenge,
            expected_rp_id=rp_id(),
            expected_origin=origin(),
        )
    except Exception as exc:
        raise AuthenticationError(f"Passkey registration failed: {exc}") from exc

    challenge_row.consumed_at = datetime.now(timezone.utc)

    cred = WebAuthnCredential(
        user_id=user.id,
        credential_id=bytes(verification.credential_id),
        public_key=bytes(verification.credential_public_key),
        sign_count=int(getattr(verification, "sign_count", 0) or 0),
        aaguid=_maybe_bytes(getattr(verification, "aaguid", None)),
        backed_up=bool(getattr(verification, "credential_backed_up", False)),
        transports=_response_transports(response),
        nickname=nickname,
    )
    db.add(cred)
    db.flush()
    return cred


# ---------------------------------------------------------------------------
# Authentication ceremony
# ---------------------------------------------------------------------------
def generate_authentication_options(db: Session, email: str) -> dict[str, Any]:
    """Build PublicKeyCredentialRequestOptions for the user with ``email``.

    Always returns a syntactically valid response — even when the email
    doesn't exist or has no credentials — so the endpoint can't be used
    as an account-enumeration oracle.
    """
    webauthn = _load_webauthn()
    user = db.scalar(select(User).where(User.email == email.lower()))
    descriptors: list = []
    if user:
        creds = list(db.scalars(
            select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
        ))
        descriptors = [
            webauthn.helpers.structs.PublicKeyCredentialDescriptor(id=c.credential_id)
            for c in creds
        ]
    options = webauthn.generate_authentication_options(
        rp_id=rp_id(),
        allow_credentials=descriptors,
    )
    _store_challenge(
        db,
        purpose="authenticate",
        challenge=options.challenge,
        user_id=user.id if user else None,
        email=email,
    )
    return webauthn.options_to_json(options)


def verify_authentication(
    db: Session,
    email: str,
    response: dict[str, Any],
) -> tuple[User, WebAuthnCredential]:
    webauthn = _load_webauthn()
    challenge_row = _find_latest_challenge(db, purpose="authenticate", email=email)
    # Look up the credential by its id (browser sends it back in ``rawId``).
    raw_id = _decode_credential_id(response)
    cred = db.scalar(
        select(WebAuthnCredential).where(WebAuthnCredential.credential_id == raw_id)
    )
    if not cred:
        raise AuthenticationError("Unknown credential")
    user = db.get(User, cred.user_id)
    if not user or not user.is_active:
        raise AuthenticationError("Unknown user")
    if challenge_row.user_id and challenge_row.user_id != user.id:
        raise AuthenticationError("Credential / challenge mismatch")

    try:
        verification = webauthn.verify_authentication_response(
            credential=response,
            expected_challenge=challenge_row.challenge,
            expected_rp_id=rp_id(),
            expected_origin=origin(),
            credential_public_key=cred.public_key,
            credential_current_sign_count=cred.sign_count,
        )
    except Exception as exc:
        raise AuthenticationError(f"Passkey authentication failed: {exc}") from exc

    new_count = int(getattr(verification, "new_sign_count", 0) or 0)
    # Replay protection: counter must strictly increase (or both be 0 for
    # authenticators that don't implement the counter at all).
    if new_count and new_count <= cred.sign_count:
        raise AuthenticationError("Passkey replay detected (sign_count did not advance)")
    cred.sign_count = new_count or cred.sign_count
    cred.last_used_at = datetime.now(timezone.utc)
    challenge_row.consumed_at = datetime.now(timezone.utc)
    db.flush()
    return user, cred


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _decode_credential_id(response: dict[str, Any]) -> bytes:
    """Pull the raw credential id out of a ``navigator.credentials.get`` result.

    Browsers serialise it as Base64URL in ``id`` / ``rawId``. The webauthn
    lib also accepts already-bytes — we cover both.
    """
    import base64

    raw = response.get("rawId") or response.get("id")
    if raw is None:
        raise AuthenticationError("Credential payload missing rawId")
    if isinstance(raw, bytes):
        return raw
    # Pad and decode as URL-safe Base64
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def _maybe_bytes(value: Any) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        # AAGUIDs come as uuid-format strings; encode the canonical form
        return value.encode()
    return None


def _response_transports(response: dict[str, Any]) -> list[str]:
    """Read the authenticator-advertised transports from the registration response."""
    transports = (
        response.get("response", {}).get("transports")
        or response.get("transports")
        or []
    )
    return [str(t) for t in transports if t]
