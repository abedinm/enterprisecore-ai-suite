"""Authentication endpoints — register, login, refresh, logout, current user.

NOTE: `from __future__ import annotations` is intentionally *not* used here.
slowapi 0.1.9's @limiter.limit decorator wraps the function with a sync trampoline
that breaks FastAPI's signature introspection when annotations are strings, leading
to "missing query param payload" errors. Real runtime annotations sidestep this.
"""
import hmac as _hmac
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated


def hmac_safe_eq(a: str, b: str) -> bool:
    """Constant-time string compare. Avoids timing side-channels when
    matching device fingerprints / tokens."""
    return _hmac.compare_digest(a or "", b or "")

from fastapi import APIRouter, Body, Depends, File, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings as app_settings
from app.core.csrf import clear_csrf_cookie, issue_csrf_cookie
from app.core.device_fingerprint import device_label, fingerprint as compute_device_fingerprint
from app.services import gamification as gam
from app.core.exceptions import AppError, AuthenticationError, ConflictError, ValidationFailed
from app.core.i18n import parse_accept_language, translate
from app.core.rate_limit import RateLimit
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    verify_and_maybe_rehash,
    verify_password,
    verify_refresh_token,
)
from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.db.session import get_db
from app.models.security import LoginAttempt
from app.models.user import RefreshToken, User
from app.schemas.auth import (
    LoginRequest,
    MfaDisableIn,
    MfaEnrollOut,
    MfaStatusOut,
    MfaVerifyIn,
    PasswordChange,
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.services.audit import record_audit

router = APIRouter()

# ---------------------------------------------------------------------------
# Cookie helpers — browsers receive httpOnly SameSite cookies so tokens
# are never accessible to JavaScript.  API/SDK clients continue to use the
# returned JSON (Bearer header) — both modes co-exist.
#
# Cookie names follow the modern ``__Host-`` prefix when (and only when) the
# Secure attribute is set — this is rejected by Chrome/Firefox unless the
# cookie is Secure, Path=/, no Domain, so we can only use it outside of
# local-HTTP development. ``deps.py`` reads both names for backward compat.
# Sliding the prefix on/off based on env is a hardening rule of Chromium's
# Web Platform Tests; see https://w3c.github.io/webappsec-cookie-store.
# ---------------------------------------------------------------------------
_COOKIE_ACCESS_MAX_AGE = app_settings.access_token_ttl_minutes * 60  # JWT exp
_COOKIE_REFRESH_MAX_AGE = app_settings.refresh_token_ttl_days * 24 * 60 * 60

# Cookie names used by the browser. We expose constants so deps.py can read
# both the new ``__Host-`` prefixed name and the legacy unprefixed one.
ACCESS_COOKIE_LEGACY = "access_token"
ACCESS_COOKIE_HOST = "__Host-access_token"
REFRESH_COOKIE_LEGACY = "refresh_token"
REFRESH_COOKIE_HOST = "__Host-refresh_token"


def _cookie_secure() -> bool:
    """Cookies set Secure outside of local development."""
    return app_settings.app_env != "development"


def _access_cookie_name() -> str:
    return ACCESS_COOKIE_HOST if _cookie_secure() else ACCESS_COOKIE_LEGACY


def _refresh_cookie_name() -> str:
    # ``__Host-`` requires Path=/ — the refresh cookie was historically scoped
    # to ``/api/v1/auth`` so we only switch when we can keep Path=/.
    return REFRESH_COOKIE_HOST if _cookie_secure() else REFRESH_COOKIE_LEGACY


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Write httpOnly auth cookies onto *response*.

    SameSite hardening:
      * access_token  → SameSite=strict (non-breaking for first-party SPA flow;
        the SPA already lives on the same origin so strict is safe and blocks
        cross-site request forgery from third-party links).
      * refresh_token → SameSite=lax so token rotation triggered by top-level
        navigations (a fresh tab on the SPA) still works.
    """
    secure = _cookie_secure()
    common = dict(httponly=True, secure=secure)
    # __Host- prefix mandates Path=/ and no Domain.
    response.set_cookie(
        _access_cookie_name(), access_token,
        max_age=_COOKIE_ACCESS_MAX_AGE, path="/", samesite="strict", **common,
    )
    # Refresh cookie also widened to Path=/ when using __Host- (the prefix
    # requires it). With the legacy name we keep the historic narrower path.
    refresh_path = "/" if secure else "/api/v1/auth"
    response.set_cookie(
        _refresh_cookie_name(), refresh_token,
        max_age=_COOKIE_REFRESH_MAX_AGE, path=refresh_path, samesite="lax", **common,
    )


def _clear_auth_cookies(response: Response) -> None:
    """Erase auth cookies — called on logout. Clears both the prefixed and
    legacy names so a deploy that toggles env can't leave a stale cookie."""
    secure = _cookie_secure()
    response.delete_cookie(ACCESS_COOKIE_LEGACY, path="/")
    response.delete_cookie(ACCESS_COOKIE_HOST, path="/")
    response.delete_cookie(REFRESH_COOKIE_LEGACY, path="/api/v1/auth")
    response.delete_cookie(REFRESH_COOKIE_LEGACY, path="/")
    response.delete_cookie(REFRESH_COOKIE_HOST, path="/" if secure else "/api/v1/auth")
    # Also clear the (non-httpOnly) CSRF cookie so the SPA boots clean.
    clear_csrf_cookie(response)


def _mint_csrf(response: Response) -> None:
    """Issue / rotate the double-submit CSRF cookie. Called on every auth
    transition (login, refresh, MFA-verify) so a stolen pre-login token
    can't be replayed against an authenticated session."""
    issue_csrf_cookie(response, secure=_cookie_secure(), samesite="lax")


def _issue_tokens(
    user: User,
    db: Session,
    *,
    request: Request | None = None,
) -> TokenResponse:
    access = create_access_token(user.id, user.role.value)
    refresh, expires_at = create_refresh_token(user.id)
    # Bind to device fingerprint at issue time. On refresh we'll require the
    # incoming request to fingerprint identically — a stolen token from a
    # different browser/network is rejected.
    ua = request.headers.get("user-agent") if request else None
    ip = _client_ip(request) if request else None
    fp = compute_device_fingerprint(ua, ip)
    label = device_label(ua, ip)
    now = datetime.now(timezone.utc)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh),
            expires_at=expires_at,
            device_fingerprint=fp,
            device_label=label,
            last_used_at=now,
            last_used_ip=ip,
        )
    )
    return TokenResponse(access_token=access, refresh_token=refresh, expires_in=60 * 60)


def _client_ip(request: Request) -> str | None:
    """Resolve the client IP, honouring X-Forwarded-For when set by a trusted
    proxy. Renders the rightmost (first hop) IP — the closest to us — so a
    malicious upstream can't spoof a lower hop. In a deployment behind a
    proxy you control, pin the trusted proxy with ``TRUSTED_PROXY_HOPS`` and
    walk that many hops from the right.
    """
    xff = request.headers.get("x-forwarded-for") if request else None
    if xff:
        # Right-most = the IP our reverse proxy saw. We trust ONE hop by
        # default; operators can widen via env, but the safest default is "1".
        hops = [h.strip() for h in xff.split(",") if h.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request and request.client else None


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RateLimit("10/minute", id="auth-register"))],
)
def register(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Legacy single-tenant registration. Attaches new users to the default
    tenant for backward-compat with single-tenant installs. New multi-tenant
    signups should go through ``/api/v1/tenants/signup`` instead, which creates
    a fresh tenant + admin in one call.
    """
    from app.models.tenant import Tenant
    email = str(payload.email).lower().strip()
    with bypass_tenant_filter():
        default = db.scalar(select(Tenant).where(Tenant.slug == "default"))
        if not default:
            raise AppError("Default tenant not provisioned", code="no_default_tenant", status_code=500)
        target_tid = default.id

    with tenant_scope(target_tid):
        if db.scalar(select(User).where(User.email == email)):
            raise ConflictError("A user with this email already exists")
        user = User(
            email=email,
            full_name=payload.full_name,
            password_hash=hash_password(payload.password),
            role=payload.role,
            department=payload.department,
            locale=payload.locale or "en",
        )
        db.add(user)
        db.flush()
        record_audit(
            db,
            actor=user,
            action="register",
            entity_type="user",
            entity_id=user.id,
            ip_address=_client_ip(request),
        )
        db.commit()
        db.refresh(user)
        return user


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(RateLimit("10/minute", id="auth-login"))],
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    email = str(payload.email).lower().strip()
    # Login is pre-auth: no tenant context is set yet, so we look up users
    # across every tenant. The user's tenant scope is then established for
    # writing the LoginAttempt + audit row.
    with bypass_tenant_filter():
        user = db.scalar(select(User).where(User.email == email))
    # Verify + transparent rehash. If the stored hash is bcrypt (pre-argon2id
    # upgrade) and the password verifies, we silently rehash with argon2id so
    # the next login is on the modern scheme. No user-visible disruption.
    rehash: str | None = None
    if user and user.is_active:
        ok, rehash = verify_and_maybe_rehash(payload.password, user.password_hash)
    else:
        ok = False
    success = bool(user and user.is_active and ok)
    if success and rehash:
        user.password_hash = rehash  # type: ignore[union-attr]

    # If we couldn't resolve the user (and thus a tenant) we still want to
    # record the failure — pin it to the default tenant so the schema
    # constraint is satisfied. Production deployments may want a dedicated
    # "system" tenant for these; for now the default tenant owns them.
    fallback_tid = None
    if not user:
        with bypass_tenant_filter():
            from app.models.tenant import Tenant
            default = db.scalar(select(Tenant).where(Tenant.slug == "default"))
            fallback_tid = default.id if default else None

    target_tid = user.tenant_id if user else fallback_tid
    with tenant_scope(target_tid):
        db.add(
            LoginAttempt(
                email=email,
                ip_address=_client_ip(request),
                success=success,
                reason=None if success else "invalid_credentials",
            )
        )
        # Localize the user-facing message based on Accept-Language. The
        # `code` field stays in English so clients matching on it (and the
        # existing tests) keep working.
        req_locale = parse_accept_language(request.headers.get("accept-language"))
        if not success or not user:
            db.commit()
            raise AuthenticationError(translate("errors.invalid_credentials", req_locale))
        if user.mfa_enabled:
            from app.core.mfa import verify as mfa_verify
            if not payload.mfa_code:
                db.commit()
                raise AppError(translate("errors.mfa_required", req_locale), code="mfa_required", status_code=401)
            if not mfa_verify(user.mfa_secret or "", payload.mfa_code):
                db.add(LoginAttempt(
                    email=email, ip_address=_client_ip(request),
                    success=False, reason="bad_mfa_code",
                ))
                db.commit()
                raise AppError(translate("errors.mfa_invalid", req_locale), code="bad_mfa_code", status_code=401)
        user.last_login_at = datetime.now(timezone.utc)
        tokens = _issue_tokens(user, db, request=request)
        # Gamification — login streak + first-time achievements. Best-effort:
        # any failure here must NOT break login itself.
        try:
            gam.award(db, tenant_id=user.tenant_id, user_id=user.id, key="welcome")
            gam.award(db, tenant_id=user.tenant_id, user_id=user.id, key="first_login")
            gam.record_streak_event(
                db, tenant_id=user.tenant_id, user_id=user.id, kind="login",
            )
            # Easter egg: signed in between 00:00 and 04:00 local-UTC.
            if 0 <= datetime.now(timezone.utc).hour < 4:
                gam.award(db, tenant_id=user.tenant_id, user_id=user.id, key="midnight_user")
            if user.mfa_enabled:
                gam.award(db, tenant_id=user.tenant_id, user_id=user.id, key="mfa_enabled")
        except Exception:  # pragma: no cover  — gamification is best-effort
            pass
        record_audit(
            db,
            actor=user,
            action="login",
            entity_type="user",
            entity_id=user.id,
            ip_address=_client_ip(request),
        )
        db.commit()
        _set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
        _mint_csrf(response)
        return tokens


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(RateLimit("60/minute", id="auth-refresh"))],
)
def refresh_tokens(
    payload: RefreshRequest | None = Body(default=None),
    request: Request = None,  # type: ignore[assignment]
    response: Response = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
) -> TokenResponse:
    # Accept the refresh token from:
    # 1) JSON body  {"refresh_token": "..."}  — existing API/test-client mode
    # 2) httpOnly cookie (either ``__Host-refresh_token`` in secure envs or the
    #    legacy ``refresh_token`` name) — browser mode (no body needed)
    raw_token = payload.refresh_token if payload else None
    if not raw_token and request is not None:
        raw_token = (
            request.cookies.get(REFRESH_COOKIE_HOST)
            or request.cookies.get(REFRESH_COOKIE_LEGACY)
        )
    if not raw_token:
        raise AuthenticationError("No refresh token provided")
    # Verify signature + expiry on the JWT itself first (fast, no DB).
    data = decode_token(raw_token, expected_type="refresh")
    user = db.get(User, data["sub"])
    if not user or not user.is_active:
        raise AuthenticationError("User account is inactive or does not exist")

    # Direct indexed lookup by HMAC-SHA256 hash — O(log n), not O(n × bcrypt).
    token_hash = hash_refresh_token(raw_token)
    matched = db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        )
    )
    if not matched:
        raise AuthenticationError("Refresh token is not recognised or has been revoked")
    expires_at = matched.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        matched.revoked_at = datetime.now(timezone.utc)
        db.commit()
        raise AuthenticationError("Refresh token expired — please sign in again")

    # Device-binding check: refuse a replay from a different browser/network.
    # Legacy tokens (issued before the device_fingerprint column existed) have
    # a NULL fingerprint and skip the check on first use; their fingerprint is
    # backfilled below so subsequent refreshes are bound.
    if matched.device_fingerprint:
        ua = request.headers.get("user-agent") if request else None
        ip = _client_ip(request) if request else None
        incoming_fp = compute_device_fingerprint(ua, ip)
        if not hmac_safe_eq(matched.device_fingerprint, incoming_fp):
            # Token theft signal: revoke this token AND every sibling token
            # for the user. Force them to re-authenticate everywhere.
            now_utc = datetime.now(timezone.utc)
            matched.revoked_at = now_utc
            for sibling in db.scalars(
                select(RefreshToken).where(
                    RefreshToken.user_id == user.id,
                    RefreshToken.revoked_at.is_(None),
                )
            ).all():
                sibling.revoked_at = now_utc
            record_audit(
                db,
                actor=user,
                action="refresh_token_device_mismatch",
                entity_type="user",
                entity_id=user.id,
                ip_address=ip,
            )
            db.commit()
            raise AuthenticationError(
                "Refresh token presented from a different device — all sessions revoked. "
                "Please sign in again.",
            )

    matched.revoked_at = datetime.now(timezone.utc)
    tokens = _issue_tokens(user, db, request=request)
    db.commit()
    if response is not None:
        _set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
        _mint_csrf(response)
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: RefreshRequest | None = None,
    request: Request = None,  # type: ignore[assignment]
    response: Response = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload and payload.refresh_token:
        # Single indexed lookup instead of linear scan + per-row hash compare.
        token_hash = hash_refresh_token(payload.refresh_token)
        match = db.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.user_id == current_user.id,
                RefreshToken.revoked_at.is_(None),
            )
        )
        if match:
            match.revoked_at = datetime.now(timezone.utc)
    else:
        tokens = db.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == current_user.id,
                RefreshToken.revoked_at.is_(None),
            )
        ).all()
        for token in tokens:
            token.revoked_at = datetime.now(timezone.utc)
    record_audit(
        db,
        actor=current_user,
        action="logout",
        entity_type="user",
        entity_id=current_user.id,
        ip_address=_client_ip(request) if request else None,
    )
    db.commit()
    if response is not None:
        _clear_auth_cookies(response)
    return None


@router.get("/sessions")
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the user's active refresh-token sessions.

    Surfaces the device label (e.g. "Chrome on Windows (203.0.113.0/24)"),
    when it was last used, and a stable id the user can revoke. Used by
    Settings → Security → Active Sessions.
    """
    rows = db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == current_user.id,
            RefreshToken.revoked_at.is_(None),
        ).order_by(RefreshToken.created_at.desc())
    ).all()
    return [
        {
            "id": r.id,
            "device_label": r.device_label or "Unknown device",
            "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
            "last_used_ip": r.last_used_ip,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        }
        for r in rows
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke a single refresh-token session (e.g. "log me out of that
    other Chrome window I left on a public computer")."""
    row = db.scalar(
        select(RefreshToken).where(
            RefreshToken.id == session_id,
            RefreshToken.user_id == current_user.id,
            RefreshToken.revoked_at.is_(None),
        )
    )
    if not row:
        raise AppError("Session not found", code="not_found", status_code=404)
    row.revoked_at = datetime.now(timezone.utc)
    record_audit(
        db,
        actor=current_user,
        action="session_revoked",
        entity_type="refresh_token",
        entity_id=session_id,
    )
    db.commit()
    return None


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserRead)
def update_me(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.department is not None:
        current_user.department = payload.department
    if payload.locale is not None:
        current_user.locale = payload.locale
    if payload.theme is not None:
        current_user.theme = payload.theme
    if payload.avatar_url is not None:
        current_user.avatar_url = payload.avatar_url
    db.commit()
    db.refresh(current_user)
    return current_user


AVATAR_DIR = "avatars"
ALLOWED_AVATAR_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2 MB before any resizing
AVATAR_MAX_DIM = 512  # downscaled to a 512×512 square for predictable sizes


def _avatar_storage_dir() -> Path:
    d = app_settings.storage_dir / "uploads" / AVATAR_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/me/avatar", response_model=UserRead)
async def upload_avatar(
    file: Annotated[UploadFile, File(...)],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a new avatar image. PNG/JPEG/WEBP only, max 2 MB.

    Image is re-encoded as PNG and resized to fit within 512×512 to strip any
    embedded metadata (EXIF GPS, ICC colour profiles, etc.) and normalise to a
    predictable on-disk size."""
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_AVATAR_TYPES:
        raise ValidationFailed(
            f"Unsupported file type {content_type!r}. Allowed: PNG, JPEG, WEBP."
        )

    raw = await file.read()
    if len(raw) > MAX_AVATAR_BYTES:
        raise ValidationFailed(
            f"Avatar is too large ({len(raw)} bytes). Max {MAX_AVATAR_BYTES // 1024} KB."
        )
    if not raw:
        raise ValidationFailed("Empty upload.")

    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover
        raise ValidationFailed("Pillow is required for image uploads on the server") from exc

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:
        raise ValidationFailed("File is not a recognisable image") from exc

    img.thumbnail((AVATAR_MAX_DIM, AVATAR_MAX_DIM))
    # Convert to RGBA for PNG; drop EXIF and other metadata.
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")

    storage_path = _avatar_storage_dir() / f"{current_user.id}.png"
    img.save(storage_path, format="PNG", optimize=True)

    # /files is mounted at app startup pointing to storage/uploads — see main.py.
    current_user.avatar_url = f"/files/{AVATAR_DIR}/{storage_path.name}"
    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
def delete_avatar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove the current user's avatar. Idempotent — succeeds even if no avatar exists."""
    storage_path = _avatar_storage_dir() / f"{current_user.id}.png"
    try:
        storage_path.unlink(missing_ok=True)
    except Exception:  # pragma: no cover  — best-effort delete
        pass
    if current_user.avatar_url:
        current_user.avatar_url = None
        db.commit()
    return None


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise AuthenticationError("Current password is incorrect")
    current_user.password_hash = hash_password(payload.new_password)
    for token in db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == current_user.id, RefreshToken.revoked_at.is_(None)
        )
    ).all():
        token.revoked_at = datetime.now(timezone.utc)
    record_audit(
        db,
        actor=current_user,
        action="password_change",
        entity_type="user",
        entity_id=current_user.id,
    )
    db.commit()
    return None


# ============== MFA (TOTP) ===============================================
@router.get("/mfa/status", response_model=MfaStatusOut)
def mfa_status(current_user: User = Depends(get_current_user)) -> MfaStatusOut:
    return MfaStatusOut(enabled=bool(current_user.mfa_enabled))


@router.post("/mfa/enroll", response_model=MfaEnrollOut)
def mfa_enroll(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MfaEnrollOut:
    """Generate (or rotate) a TOTP secret for the current user.

    Stores the secret Fernet-encrypted but leaves ``mfa_enabled = False`` —
    the user must then call /mfa/verify with a fresh code to flip it on.
    That prevents an interrupted enrolment from locking them out.
    """
    from app.core import mfa as mfa_mod
    secret = mfa_mod.new_secret()
    current_user.mfa_secret = mfa_mod.encrypt_secret(secret)
    current_user.mfa_enabled = False  # not active until verified
    db.commit()
    uri = mfa_mod.provisioning_uri(secret, current_user.email)
    return MfaEnrollOut(
        secret=secret,
        otpauth_url=uri,
        qr_png_base64=mfa_mod.qr_png_b64(uri),
    )


@router.post("/mfa/verify", status_code=status.HTTP_204_NO_CONTENT)
def mfa_verify_enrol(
    payload: MfaVerifyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Confirm enrolment by submitting a fresh TOTP code. Flips on mfa_enabled."""
    from app.core import mfa as mfa_mod
    if not current_user.mfa_secret:
        raise AppError("No MFA enrolment in progress — call /mfa/enroll first",
                      code="mfa_not_enrolled", status_code=400)
    if not mfa_mod.verify(current_user.mfa_secret, payload.code):
        raise AppError("Invalid MFA code", code="bad_mfa_code", status_code=401)
    current_user.mfa_enabled = True
    record_audit(db, actor=current_user, action="mfa_enabled",
                entity_type="user", entity_id=current_user.id)
    db.commit()
    return None


@router.post("/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
def mfa_disable(
    payload: MfaDisableIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Disable MFA. Requires both the current password AND a valid TOTP code
    so a stolen access token alone cannot remove the second factor."""
    from app.core import mfa as mfa_mod
    if not verify_password(payload.password, current_user.password_hash):
        raise AuthenticationError("Current password is incorrect")
    if not current_user.mfa_enabled or not current_user.mfa_secret:
        raise AppError("MFA is not currently enabled", code="mfa_not_enabled", status_code=400)
    if not mfa_mod.verify(current_user.mfa_secret, payload.code):
        raise AppError("Invalid MFA code", code="bad_mfa_code", status_code=401)
    current_user.mfa_secret = None
    current_user.mfa_enabled = False
    record_audit(db, actor=current_user, action="mfa_disabled",
                entity_type="user", entity_id=current_user.id)
    db.commit()
    return None
