"""Authentication, password hashing, JWT, and lightweight encryption helpers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ValidationFailed

__all__ = [
    "verify_password",
    "verify_and_maybe_rehash",
    "hash_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_refresh_token",
    "verify_refresh_token",
]

ALGORITHM = "HS256"
# Password hashing — argon2id by default (OWASP 2024 recommendation), with
# bcrypt kept around so users hashed before the upgrade still verify. When a
# bcrypt-hashed user logs in we transparently rehash with argon2id; passlib's
# ``needs_update`` flags any scheme that isn't the first in the list. The
# rehash happens at the call site (see ``verify_and_maybe_rehash`` below).
#
# argon2 parameters target ~50ms on modern server CPUs:
#   memory=65536 KiB (64 MiB), time=3, parallelism=4
# These are the OWASP 2024 minimums; tune up if the host has spare RAM.
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated="auto",
    argon2__memory_cost=65536,
    argon2__time_cost=3,
    argon2__parallelism=4,
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Constant-time verify against any supported scheme (argon2 / bcrypt)."""
    return pwd_context.verify(plain_password, hashed_password)


def verify_and_maybe_rehash(plain_password: str, hashed_password: str) -> tuple[bool, str | None]:
    """Verify *plain_password* and, if the stored hash is using a deprecated
    scheme (e.g. bcrypt after the argon2id upgrade), return a fresh hash so
    the caller can persist it. Returns ``(ok, new_hash_or_None)``.
    """
    ok = pwd_context.verify(plain_password, hashed_password)
    if not ok:
        return False, None
    if pwd_context.needs_update(hashed_password):
        return True, pwd_context.hash(plain_password)
    return True, None


def hash_password(password: str) -> str:
    if len(password) < settings.password_min_length:
        raise ValidationFailed(f"Password must be at least {settings.password_min_length} characters long")
    return pwd_context.hash(password)


def create_access_token(subject: str, role: str, expires_delta: timedelta | None = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.access_token_ttl_minutes))
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": expire,
        "iat": now,
        "type": "access",
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(subject: str) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.refresh_token_ttl_days)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expires_at,
        "iat": now,
        "type": "refresh",
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), expires_at


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise AuthenticationError("Invalid or expired token") from exc
    if payload.get("type") != expected_type:
        raise AuthenticationError("Invalid token type")
    return payload


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """Return a Fernet instance with a STABLE key.

    If ``ENCRYPTION_KEY`` is unset we derive a deterministic key from
    ``SECRET_KEY`` so that data encrypted across restarts can still be read.
    Previously this function generated a new random key on every call when
    ``ENCRYPTION_KEY`` was empty, which made every decrypt fail.
    """
    raw = settings.encryption_key
    if raw:
        key = raw.encode() if isinstance(raw, str) else raw
    else:
        digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh-token JWT for storage. Bcrypt truncates at 72 chars and JWTs share
    a long static prefix per user, which would make every issued refresh token verify
    against every stored hash. SHA-256 keyed with the app secret avoids that collision."""
    digest = hmac.new(settings.secret_key.encode(), token.encode(), hashlib.sha256).hexdigest()
    return digest


def verify_refresh_token(token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_refresh_token(token), stored_hash)


def encrypt_text(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_text(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValidationFailed("Unable to decrypt value with the configured encryption key") from exc
