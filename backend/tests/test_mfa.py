"""TOTP MFA: enroll, verify, login challenge, disable."""
from __future__ import annotations

import pyotp

from app.core.mfa import decrypt_secret
from app.models.user import User


def _admin(db) -> User:
    from sqlalchemy import select
    return db.scalar(select(User).where(User.email == "admin@local"))


def test_status_default_false(client, auth_headers):
    r = client.get("/api/v1/auth/mfa/status", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_enroll_returns_secret_and_qr(client, auth_headers):
    r = client.post("/api/v1/auth/mfa/enroll", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["secret"]
    assert body["otpauth_url"].startswith("otpauth://totp/")
    # qr_png_base64 should be a non-trivial PNG payload
    assert len(body["qr_png_base64"]) > 200
    # NOT enabled yet — must verify with a code first
    status_r = client.get("/api/v1/auth/mfa/status", headers=auth_headers)
    assert status_r.json()["enabled"] is False


def test_enroll_then_verify_flips_enabled(client, auth_headers, db):
    enroll = client.post("/api/v1/auth/mfa/enroll", headers=auth_headers).json()
    code = pyotp.TOTP(enroll["secret"]).now()
    v = client.post("/api/v1/auth/mfa/verify", headers=auth_headers, json={"code": code})
    assert v.status_code == 204, v.text
    db.expire_all()
    admin = _admin(db)
    assert admin.mfa_enabled is True
    assert admin.mfa_secret  # encrypted blob present
    # And decryptable
    assert decrypt_secret(admin.mfa_secret) == enroll["secret"]


def test_verify_with_bad_code_does_not_enable(client, auth_headers, db):
    client.post("/api/v1/auth/mfa/enroll", headers=auth_headers)
    r = client.post("/api/v1/auth/mfa/verify", headers=auth_headers, json={"code": "000000"})
    assert r.status_code == 401
    assert r.json()["code"] == "bad_mfa_code"
    db.expire_all()
    assert _admin(db).mfa_enabled is False


def test_login_blocked_without_mfa_code(client, auth_headers, db):
    # Enrol + enable
    enroll = client.post("/api/v1/auth/mfa/enroll", headers=auth_headers).json()
    code = pyotp.TOTP(enroll["secret"]).now()
    client.post("/api/v1/auth/mfa/verify", headers=auth_headers, json={"code": code})
    # Now login WITHOUT a code — must be rejected
    r = client.post("/api/v1/auth/login",
                    json={"email": "admin@local", "password": "ChangeMe123!"})
    assert r.status_code == 401
    assert r.json()["code"] == "mfa_required"


def test_login_succeeds_with_valid_mfa_code(client, auth_headers, db):
    enroll = client.post("/api/v1/auth/mfa/enroll", headers=auth_headers).json()
    code = pyotp.TOTP(enroll["secret"]).now()
    client.post("/api/v1/auth/mfa/verify", headers=auth_headers, json={"code": code})

    fresh_code = pyotp.TOTP(enroll["secret"]).now()
    r = client.post("/api/v1/auth/login", json={
        "email": "admin@local", "password": "ChangeMe123!", "mfa_code": fresh_code,
    })
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]


def test_login_rejected_with_wrong_mfa_code(client, auth_headers, db):
    enroll = client.post("/api/v1/auth/mfa/enroll", headers=auth_headers).json()
    code = pyotp.TOTP(enroll["secret"]).now()
    client.post("/api/v1/auth/mfa/verify", headers=auth_headers, json={"code": code})

    r = client.post("/api/v1/auth/login", json={
        "email": "admin@local", "password": "ChangeMe123!", "mfa_code": "999999",
    })
    assert r.status_code == 401
    assert r.json()["code"] == "bad_mfa_code"


def test_disable_requires_password_and_code(client, auth_headers, db):
    enroll = client.post("/api/v1/auth/mfa/enroll", headers=auth_headers).json()
    code = pyotp.TOTP(enroll["secret"]).now()
    client.post("/api/v1/auth/mfa/verify", headers=auth_headers, json={"code": code})

    # Wrong password
    r1 = client.post("/api/v1/auth/mfa/disable", headers=auth_headers, json={
        "password": "wrong", "code": pyotp.TOTP(enroll["secret"]).now(),
    })
    assert r1.status_code == 401

    # Wrong code
    r2 = client.post("/api/v1/auth/mfa/disable", headers=auth_headers, json={
        "password": "ChangeMe123!", "code": "000000",
    })
    assert r2.status_code == 401

    # Both correct → disables
    r3 = client.post("/api/v1/auth/mfa/disable", headers=auth_headers, json={
        "password": "ChangeMe123!", "code": pyotp.TOTP(enroll["secret"]).now(),
    })
    assert r3.status_code == 204
    db.expire_all()
    admin = _admin(db)
    assert admin.mfa_enabled is False
    assert admin.mfa_secret is None
