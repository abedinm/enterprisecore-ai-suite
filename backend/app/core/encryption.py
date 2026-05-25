"""Per-tenant field-level encryption with BYOK envelope encryption.

The existing :mod:`app.core.security` module ships a single global Fernet
key derived from ``SECRET_KEY``. That's fine for a single-tenant install,
but for multi-tenancy + enterprise BYOK we need a per-tenant Data
Encryption Key (DEK) that customers can wrap with their own KMS.

Envelope encryption:

* The **master key** wraps the **DEK**. Master can be (a) the server's
  Fernet key, or (b) a customer's KMS-managed key when BYOK is enabled.
* The **DEK** is a 32-byte Fernet key that lives only in process memory
  (loaded into a contextvar at request start, never persisted).
* Field ciphertext carries a version prefix ``v<n>:<fernet_token>`` so
  we can rotate DEKs and still read old data.

Ciphertext format::

    v<key_version>:<urlsafe_base64_fernet_token>

Rotation flow:
  1. ``rotate_tenant_dek`` mints a new DEK row at v(n+1), wraps it with
     the same KMS provider, marks the old row inactive.
  2. A background job walks every encrypted field and re-encrypts under
     the new DEK. Until done, both rows stay readable.
"""
from __future__ import annotations

import base64
import logging
import os
import secrets
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationFailed
from app.core.security import _fernet  # type: ignore  # internal helper reuse
from app.models.security_hardening import TenantEncryptionKey

logger = logging.getLogger(__name__)

# Per-request DEK cache. Keyed by (tenant_id, key_version) → raw 32-byte
# Fernet key. We cache by version too so a request that reads two
# different versions during rotation doesn't pay to unwrap twice.
_dek_ctx: ContextVar[dict[tuple[str, int], bytes]] = ContextVar(
    "tenant_dek_cache", default={}
)


# ---------------------------------------------------------------------------
# KMS providers — pluggable, optional. Each provider must implement
# wrap(plaintext_dek, key_ref) -> bytes and unwrap(wrapped_dek, key_ref) -> bytes.
# ---------------------------------------------------------------------------
def _server_wrap(plaintext: bytes, _key_ref: str | None) -> bytes:
    """Default: wrap the DEK with the server's Fernet master key.

    The result is opaque bytes; we round-trip through the application-
    level Fernet so an operator rotating ``ENCRYPTION_KEY`` re-wraps
    every tenant DEK on next read.
    """
    return _fernet().encrypt(plaintext)


def _server_unwrap(wrapped: bytes, _key_ref: str | None) -> bytes:
    return _fernet().decrypt(wrapped)


def _kms_provider(name: str):
    """Resolve a KMS provider's (wrap, unwrap) pair. Falls back to the
    server-managed pair with a warning if the backing library isn't
    installed. Customers who want true BYOK install ``requirements-byok.txt``.
    """
    if name == "server":
        return _server_wrap, _server_unwrap
    try:
        if name == "aws_kms":
            from app.core.kms import aws_kms as mod  # type: ignore
        elif name == "gcp_kms":
            from app.core.kms import gcp_kms as mod  # type: ignore
        elif name == "azure_kv":
            from app.core.kms import azure_kv as mod  # type: ignore
        elif name == "hcv_transit":
            from app.core.kms import hcv_transit as mod  # type: ignore
        else:
            raise ValidationFailed(f"Unknown KMS provider: {name}")
        return mod.wrap, mod.unwrap
    except ImportError:
        logger.warning(
            "KMS provider %s requested but its library is not installed — "
            "falling back to server-managed wrapping. Install "
            "requirements-byok.txt to enable BYOK.",
            name,
        )
        return _server_wrap, _server_unwrap


# ---------------------------------------------------------------------------
# DEK lifecycle
# ---------------------------------------------------------------------------
def _generate_dek() -> bytes:
    """Generate a fresh 32-byte URL-safe Fernet key."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32))


def ensure_tenant_dek(tenant_id: str, db: Session) -> TenantEncryptionKey:
    """Look up the active DEK for a tenant, lazily provisioning one if
    none exists. Called by the encryption middleware at request start —
    so a tenant created before this migration ran transparently gets a
    v1 key on first encrypt/decrypt.
    """
    from app.core.tenant_context import bypass_tenant_filter

    with bypass_tenant_filter():
        row = db.scalar(
            select(TenantEncryptionKey)
            .where(
                TenantEncryptionKey.tenant_id == tenant_id,
                TenantEncryptionKey.is_active.is_(True),
            )
            .order_by(TenantEncryptionKey.key_version.desc())
        )
        if row:
            return row
        # Lazy-create v1.
        plaintext = _generate_dek()
        wrapped = _server_wrap(plaintext, None)
        row = TenantEncryptionKey(
            tenant_id=tenant_id,
            key_version=1,
            wrapped_dek=wrapped,
            kms_provider="server",
            kms_key_ref=None,
            is_active=True,
            activated_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row


def _unwrap_dek(row: TenantEncryptionKey) -> bytes:
    """Unwrap a stored DEK to its raw 32-byte Fernet key."""
    _wrap, unwrap = _kms_provider(row.kms_provider)
    return unwrap(row.wrapped_dek, row.kms_key_ref)


def get_tenant_dek(tenant_id: str, db: Session, key_version: int | None = None) -> bytes:
    """Return the unwrapped DEK for this tenant (raw 32-byte Fernet key).

    If ``key_version`` is None, returns the currently-active DEK. When
    decrypting historic data we pass the version parsed from the
    ciphertext prefix so rotation-in-progress works.

    Cached in a contextvar for the duration of the request so we don't
    re-unwrap on every field decrypt.
    """
    cache = _dek_ctx.get()
    if key_version is None:
        row = ensure_tenant_dek(tenant_id, db)
        key_version = row.key_version
    else:
        from app.core.tenant_context import bypass_tenant_filter
        with bypass_tenant_filter():
            row = db.scalar(
                select(TenantEncryptionKey)
                .where(
                    TenantEncryptionKey.tenant_id == tenant_id,
                    TenantEncryptionKey.key_version == key_version,
                )
            )
        if not row:
            raise NotFoundError(
                f"Encryption key v{key_version} for tenant {tenant_id} not found"
            )

    cache_key = (tenant_id, key_version)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    raw = _unwrap_dek(row)
    # Mutate the cache dict in place — contextvar carries the same dict
    # for the life of the task.
    cache[cache_key] = raw
    _dek_ctx.set(cache)
    return raw


# ---------------------------------------------------------------------------
# Field encrypt / decrypt
# ---------------------------------------------------------------------------
def _build_db_session() -> Session:
    """Open an ad-hoc session when the caller didn't pass one. Used by
    the simple ``encrypt_field(plaintext, tenant_id)`` signature."""
    from app.db.session import SessionLocal
    return SessionLocal()


def encrypt_field(plaintext: str, tenant_id: str, db: Session | None = None) -> str:
    """Encrypt ``plaintext`` with the tenant's currently-active DEK.

    Returns a string of the form ``v<version>:<token>``.
    """
    own_session = db is None
    db = db or _build_db_session()
    try:
        row = ensure_tenant_dek(tenant_id, db)
        dek = get_tenant_dek(tenant_id, db, row.key_version)
        token = Fernet(dek).encrypt(plaintext.encode("utf-8")).decode("ascii")
        return f"v{row.key_version}:{token}"
    finally:
        if own_session:
            db.close()


def decrypt_field(ciphertext: str, tenant_id: str, db: Session | None = None) -> str:
    """Decrypt a versioned ciphertext produced by :func:`encrypt_field`.

    For backward-compatibility with rows encrypted by the legacy global
    Fernet (no version prefix), we fall back to the server master key
    when the prefix is missing.
    """
    if not ciphertext:
        return ciphertext
    own_session = db is None
    db = db or _build_db_session()
    try:
        if ciphertext.startswith("v") and ":" in ciphertext:
            prefix, token = ciphertext.split(":", 1)
            try:
                version = int(prefix[1:])
            except ValueError as exc:
                raise ValidationFailed("Malformed ciphertext version prefix") from exc
            dek = get_tenant_dek(tenant_id, db, version)
            try:
                return Fernet(dek).decrypt(token.encode("ascii")).decode("utf-8")
            except InvalidToken as exc:
                raise ValidationFailed("Unable to decrypt: wrong tenant DEK or corrupt ciphertext") from exc
        # Legacy global-Fernet ciphertext.
        from app.core.security import decrypt_text
        return decrypt_text(ciphertext)
    finally:
        if own_session:
            db.close()


# ---------------------------------------------------------------------------
# Rotation + BYOK
# ---------------------------------------------------------------------------
def rotate_tenant_dek(tenant_id: str, db: Session) -> TenantEncryptionKey:
    """Mint a new DEK at v(n+1), wrap with the current KMS provider,
    flip the old row's ``is_active`` to False.

    Note: this only mints the new key. Re-encrypting existing ciphertext
    is the caller's job (a background migration). Until that completes,
    both versions stay readable thanks to the version prefix.
    """
    from app.core.tenant_context import bypass_tenant_filter

    with bypass_tenant_filter():
        current = db.scalar(
            select(TenantEncryptionKey)
            .where(
                TenantEncryptionKey.tenant_id == tenant_id,
                TenantEncryptionKey.is_active.is_(True),
            )
            .order_by(TenantEncryptionKey.key_version.desc())
        )
        if not current:
            return ensure_tenant_dek(tenant_id, db)
        new_version = current.key_version + 1
        plaintext = _generate_dek()
        wrap, _unwrap = _kms_provider(current.kms_provider)
        wrapped = wrap(plaintext, current.kms_key_ref)
        new_row = TenantEncryptionKey(
            tenant_id=tenant_id,
            key_version=new_version,
            wrapped_dek=wrapped,
            kms_provider=current.kms_provider,
            kms_key_ref=current.kms_key_ref,
            is_active=True,
            activated_at=datetime.now(timezone.utc),
        )
        current.is_active = False
        current.rotated_at = datetime.now(timezone.utc)
        db.add(new_row)
        db.commit()
        db.refresh(new_row)

        # Drop the per-request cache so the next encrypt picks the new
        # version (this matters mostly inside long-running tests).
        _dek_ctx.set({})
        return new_row


def switch_to_byok(
    tenant_id: str,
    kms_provider: str,
    kms_key_ref: str,
    db: Session,
) -> TenantEncryptionKey:
    """Re-wrap the tenant's current DEK using the customer's KMS.

    Steps:
      1. Unwrap the existing DEK with the current provider.
      2. Wrap it again with the new provider + key ref.
      3. Persist as a NEW version row (BYOK switch counts as a rotation).
      4. Mark the previous row inactive.
    """
    from app.core.tenant_context import bypass_tenant_filter

    if kms_provider not in ("server", "aws_kms", "gcp_kms", "azure_kv", "hcv_transit"):
        raise ValidationFailed(f"Unknown KMS provider: {kms_provider}")

    with bypass_tenant_filter():
        current = db.scalar(
            select(TenantEncryptionKey)
            .where(
                TenantEncryptionKey.tenant_id == tenant_id,
                TenantEncryptionKey.is_active.is_(True),
            )
            .order_by(TenantEncryptionKey.key_version.desc())
        )
        if not current:
            current = ensure_tenant_dek(tenant_id, db)
        # Unwrap with the OLD provider.
        raw_dek = _unwrap_dek(current)
        # Wrap with the NEW provider.
        wrap, _unwrap = _kms_provider(kms_provider)
        new_wrapped = wrap(raw_dek, kms_key_ref)
        new_version = current.key_version + 1
        new_row = TenantEncryptionKey(
            tenant_id=tenant_id,
            key_version=new_version,
            wrapped_dek=new_wrapped,
            kms_provider=kms_provider,
            kms_key_ref=kms_key_ref,
            is_active=True,
            activated_at=datetime.now(timezone.utc),
        )
        current.is_active = False
        current.rotated_at = datetime.now(timezone.utc)
        db.add(new_row)
        db.commit()
        db.refresh(new_row)
        _dek_ctx.set({})
        return new_row


# ---------------------------------------------------------------------------
# Public convenience for callers that don't have a tenant_id explicitly
# ---------------------------------------------------------------------------
def encrypt_field_for_current_tenant(plaintext: str) -> str:
    """Encrypt with the current request's tenant DEK. Falls back to the
    legacy global Fernet when no tenant context is set (system tasks)."""
    from app.core.tenant_context import get_current_tenant_id

    tid = get_current_tenant_id()
    if not tid:
        from app.core.security import encrypt_text
        return encrypt_text(plaintext)
    return encrypt_field(plaintext, tid)


def decrypt_field_for_current_tenant(ciphertext: str) -> str:
    from app.core.tenant_context import get_current_tenant_id

    tid = get_current_tenant_id()
    if not tid:
        from app.core.security import decrypt_text
        return decrypt_text(ciphertext)
    return decrypt_field(ciphertext, tid)
