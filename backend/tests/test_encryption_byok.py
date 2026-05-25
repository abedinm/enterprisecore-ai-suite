"""Tests for per-tenant field-level encryption + BYOK envelope."""
from __future__ import annotations

import base64
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core.encryption import (
    decrypt_field, encrypt_field, ensure_tenant_dek, get_tenant_dek,
    rotate_tenant_dek, switch_to_byok,
)
from app.core.tenant_context import tenant_scope
from app.models.security_hardening import TenantEncryptionKey


def test_encrypt_decrypt_roundtrip(db, default_tenant):
    plaintext = "super-secret-api-key-12345"
    ciphertext = encrypt_field(plaintext, default_tenant.id, db)
    assert ciphertext.startswith("v")
    assert ":" in ciphertext
    assert plaintext not in ciphertext  # the plaintext shouldn't leak

    recovered = decrypt_field(ciphertext, default_tenant.id, db)
    assert recovered == plaintext


def test_cross_tenant_ciphertext_unreadable(session_factory, make_tenant):
    tenant_a, _, _ = make_tenant("enc-a")
    tenant_b, _, _ = make_tenant("enc-b")

    with session_factory() as db_a, tenant_scope(tenant_a.id):
        ensure_tenant_dek(tenant_a.id, db_a)
        ct = encrypt_field("tenant-a-secret", tenant_a.id, db_a)
    with session_factory() as db_b, tenant_scope(tenant_b.id):
        ensure_tenant_dek(tenant_b.id, db_b)
        # Attempting to decrypt A's ciphertext with B's DEK must fail.
        from app.core.exceptions import ValidationFailed
        with pytest.raises(ValidationFailed):
            decrypt_field(ct, tenant_b.id, db_b)


def test_rotation_old_ciphertext_still_readable(db, make_tenant, session_factory):
    tenant, _, _ = make_tenant("enc-rotate")
    with session_factory() as s, tenant_scope(tenant.id):
        ensure_tenant_dek(tenant.id, s)
        ct_v1 = encrypt_field("pre-rotation-payload", tenant.id, s)
        old_row = s.scalar(
            select(TenantEncryptionKey)
            .where(TenantEncryptionKey.tenant_id == tenant.id, TenantEncryptionKey.is_active.is_(True))
        )
        assert old_row.key_version == 1

        new_row = rotate_tenant_dek(tenant.id, s)
        assert new_row.key_version == 2

        # New writes use v2.
        ct_v2 = encrypt_field("post-rotation-payload", tenant.id, s)
        assert ct_v2.startswith("v2:")

        # Old v1 ciphertext is still readable.
        assert decrypt_field(ct_v1, tenant.id, s) == "pre-rotation-payload"
        assert decrypt_field(ct_v2, tenant.id, s) == "post-rotation-payload"


def test_byok_switch_with_mocked_kms(make_tenant, session_factory):
    """Switch a tenant to BYOK with a stubbed KMS provider and confirm the
    DEK is re-wrapped via that provider but plaintext stays readable."""
    tenant, _, _ = make_tenant("enc-byok")

    # Build a fake KMS that just prepends bytes so we can confirm it was used.
    fake_calls = {"wrap": 0, "unwrap": 0}

    def _fake_wrap(plaintext: bytes, key_ref: str) -> bytes:
        fake_calls["wrap"] += 1
        return b"FAKE:" + plaintext

    def _fake_unwrap(wrapped: bytes, key_ref: str) -> bytes:
        fake_calls["unwrap"] += 1
        assert wrapped.startswith(b"FAKE:")
        return wrapped[len(b"FAKE:"):]

    with patch("app.core.encryption._kms_provider") as mock_provider:
        mock_provider.side_effect = lambda name: (
            (_fake_wrap, _fake_unwrap) if name == "aws_kms"
            else (
                __import__("app.core.encryption", fromlist=["_server_wrap"])._server_wrap,
                __import__("app.core.encryption", fromlist=["_server_unwrap"])._server_unwrap,
            )
        )
        with session_factory() as s, tenant_scope(tenant.id):
            ensure_tenant_dek(tenant.id, s)
            new_row = switch_to_byok(
                tenant_id=tenant.id,
                kms_provider="aws_kms",
                kms_key_ref="arn:aws:kms:us-east-1:000000000000:key/test",
                db=s,
            )
            assert new_row.kms_provider == "aws_kms"
            assert new_row.kms_key_ref.startswith("arn:aws:kms:")
            assert fake_calls["wrap"] >= 1

            # Field encrypt/decrypt still works under the new provider.
            ct = encrypt_field("after-byok", tenant.id, s)
            assert decrypt_field(ct, tenant.id, s) == "after-byok"
            assert fake_calls["unwrap"] >= 1


def test_lazy_dek_provisioning(make_tenant, session_factory):
    tenant, _, _ = make_tenant("enc-lazy")
    with session_factory() as s, tenant_scope(tenant.id):
        # No row exists yet.
        existing = s.scalar(
            select(TenantEncryptionKey).where(TenantEncryptionKey.tenant_id == tenant.id)
        )
        assert existing is None
        # First encrypt provisions one.
        encrypt_field("hello", tenant.id, s)
        row = s.scalar(
            select(TenantEncryptionKey).where(TenantEncryptionKey.tenant_id == tenant.id)
        )
        assert row is not None
        assert row.key_version == 1
        assert row.kms_provider == "server"
