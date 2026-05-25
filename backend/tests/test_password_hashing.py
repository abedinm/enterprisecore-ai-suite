"""Password hashing: argon2id default + bcrypt back-compat."""
from __future__ import annotations

from app.core.security import (
    hash_password,
    verify_and_maybe_rehash,
    verify_password,
)


def test_new_hashes_use_argon2id():
    h = hash_password("CorrectHorseBatteryStaple")
    assert h.startswith("$argon2id$"), h


def test_argon2id_hash_round_trips():
    h = hash_password("CorrectHorseBatteryStaple")
    assert verify_password("CorrectHorseBatteryStaple", h)
    assert not verify_password("wrong", h)


def test_legacy_bcrypt_still_verifies():
    """Users hashed before the argon2id upgrade must still log in."""
    from passlib.context import CryptContext
    legacy = CryptContext(schemes=["bcrypt"], deprecated="auto")
    bcrypt_hash = legacy.hash("LegacyPassword123!")
    assert verify_password("LegacyPassword123!", bcrypt_hash)


def test_verify_and_maybe_rehash_upgrades_bcrypt():
    """On successful login against a bcrypt hash, the caller gets a fresh
    argon2id hash to persist."""
    from passlib.context import CryptContext
    legacy = CryptContext(schemes=["bcrypt"], deprecated="auto")
    bcrypt_hash = legacy.hash("LegacyPassword123!")
    ok, new_hash = verify_and_maybe_rehash("LegacyPassword123!", bcrypt_hash)
    assert ok is True
    assert new_hash is not None
    assert new_hash.startswith("$argon2id$")


def test_verify_and_maybe_rehash_no_op_on_argon2():
    """An already-argon2id hash should not be rehashed."""
    h = hash_password("NewPassword!")
    ok, new_hash = verify_and_maybe_rehash("NewPassword!", h)
    assert ok is True
    assert new_hash is None


def test_verify_and_maybe_rehash_fails_on_wrong_password():
    h = hash_password("rightright1")
    ok, new_hash = verify_and_maybe_rehash("wrongwrong1", h)
    assert ok is False and new_hash is None
