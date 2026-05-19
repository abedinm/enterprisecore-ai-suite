"""Authentication endpoints — register, login, refresh, logout, current user.

NOTE: `from __future__ import annotations` is intentionally *not* used here.
slowapi 0.1.9's @limiter.limit decorator wraps the function with a sync trampoline
that breaks FastAPI's signature introspection when annotations are strings, leading
to "missing query param payload" errors. Real runtime annotations sidestep this.
"""
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings as app_settings
from app.core.exceptions import AuthenticationError, ConflictError, ValidationFailed
from app.core.rate_limit import RateLimit
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    verify_password,
    verify_refresh_token,
)
from app.db.session import get_db
from app.models.security import LoginAttempt
from app.models.user import RefreshToken, User
from app.schemas.auth import (
    LoginRequest,
    PasswordChange,
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.services.audit import record_audit

router = APIRouter()


def _issue_tokens(user: User, db: Session) -> TokenResponse:
    access = create_access_token(user.id, user.role.value)
    refresh, expires_at = create_refresh_token(user.id)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh),
            expires_at=expires_at,
        )
    )
    return TokenResponse(access_token=access, refresh_token=refresh, expires_in=60 * 60)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


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
    email = str(payload.email).lower().strip()
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
    db: Session = Depends(get_db),
) -> TokenResponse:
    email = str(payload.email).lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    success = bool(user and user.is_active and verify_password(payload.password, user.password_hash))
    db.add(
        LoginAttempt(
            email=email,
            ip_address=_client_ip(request),
            success=success,
            reason=None if success else "invalid_credentials",
        )
    )
    if not success or not user:
        db.commit()
        raise AuthenticationError("Invalid email or password")
    user.last_login_at = datetime.now(timezone.utc)
    tokens = _issue_tokens(user, db)
    record_audit(
        db,
        actor=user,
        action="login",
        entity_type="user",
        entity_id=user.id,
        ip_address=_client_ip(request),
    )
    db.commit()
    return tokens


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(RateLimit("60/minute", id="auth-refresh"))],
)
def refresh_tokens(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    # Verify signature + expiry on the JWT itself first (fast, no DB).
    data = decode_token(payload.refresh_token, expected_type="refresh")
    user = db.get(User, data["sub"])
    if not user or not user.is_active:
        raise AuthenticationError("User account is inactive or does not exist")

    # Direct indexed lookup by HMAC-SHA256 hash — O(log n), not O(n × bcrypt).
    token_hash = hash_refresh_token(payload.refresh_token)
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

    matched.revoked_at = datetime.now(timezone.utc)
    tokens = _issue_tokens(user, db)
    db.commit()
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: RefreshRequest | None = None,
    request: Request = None,  # type: ignore[assignment]
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
