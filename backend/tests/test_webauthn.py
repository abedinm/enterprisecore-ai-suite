"""WebAuthn passkey endpoint tests.

The ``webauthn`` PyPI lib's verify functions are mocked so the tests
don't need to perform real attestation / assertion crypto. Each test
patches the symbols inside :mod:`app.services.webauthn` so the
endpoint module sees the mocked values transitively.
"""
from __future__ import annotations

import base64
import sys
import types
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.models.webauthn import WebAuthnChallenge, WebAuthnCredential


# ---------------------------------------------------------------------------
# webauthn-lib stub installed before app.services.webauthn first imports it
# ---------------------------------------------------------------------------
@dataclass
class _RegResult:
    credential_id: bytes
    credential_public_key: bytes
    sign_count: int = 0
    aaguid: bytes | None = None
    credential_backed_up: bool = False


@dataclass
class _AuthResult:
    new_sign_count: int = 1


class _StubOptions:
    """Mimic the lib's options object — exposes ``challenge`` + serialises to JSON."""

    def __init__(self, challenge: bytes):
        self.challenge = challenge


def _install_webauthn_stub():
    """Drop a minimal ``webauthn`` module into sys.modules.

    Lets ``app.services.webauthn`` import without the real lib being
    installed — every test then re-patches symbols on the SERVICE module
    to control specific behaviour.
    """
    if "webauthn" in sys.modules:
        return
    mod = types.ModuleType("webauthn")
    helpers = types.ModuleType("webauthn.helpers")
    structs = types.ModuleType("webauthn.helpers.structs")

    @dataclass
    class PublicKeyCredentialDescriptor:
        id: bytes

    class AuthenticatorSelectionCriteria:  # pragma: no cover - structural only
        pass

    class UserVerificationRequirement:  # pragma: no cover - structural only
        REQUIRED = "required"
        PREFERRED = "preferred"

    structs.PublicKeyCredentialDescriptor = PublicKeyCredentialDescriptor
    structs.AuthenticatorSelectionCriteria = AuthenticatorSelectionCriteria
    structs.UserVerificationRequirement = UserVerificationRequirement
    helpers.structs = structs
    mod.helpers = helpers

    def generate_registration_options(**kw):
        return _StubOptions(challenge=b"reg-challenge")

    def generate_authentication_options(**kw):
        return _StubOptions(challenge=b"auth-challenge")

    def verify_registration_response(**kw):
        return _RegResult(
            credential_id=b"cred-id-1",
            credential_public_key=b"pubkey-bytes",
            sign_count=0,
            credential_backed_up=True,
        )

    def verify_authentication_response(**kw):
        return _AuthResult(new_sign_count=1)

    def options_to_json(options):
        return '{"publicKey": {"challenge": "stub"}}'

    mod.generate_registration_options = generate_registration_options
    mod.generate_authentication_options = generate_authentication_options
    mod.verify_registration_response = verify_registration_response
    mod.verify_authentication_response = verify_authentication_response
    mod.options_to_json = options_to_json

    sys.modules["webauthn"] = mod
    sys.modules["webauthn.helpers"] = helpers
    sys.modules["webauthn.helpers.structs"] = structs


_install_webauthn_stub()


# Convenience: a typical browser-shaped credential payload for finish/
# endpoints. The contents don't matter — the webauthn lib is mocked.
_RAW_CRED_ID = b"cred-id-1"
_CRED_ID_B64 = base64.urlsafe_b64encode(_RAW_CRED_ID).rstrip(b"=").decode()
DUMMY_CREDENTIAL = {
    "id": _CRED_ID_B64,
    "rawId": _CRED_ID_B64,
    "type": "public-key",
    "response": {
        "clientDataJSON": "stub",
        "attestationObject": "stub",
        "transports": ["internal"],
    },
}


@pytest.fixture
def webauthn_lib(monkeypatch):
    """Re-apply default mocks on every test (so tests can override individual ones)."""
    import app.services.webauthn as svc

    def gen_reg(**kw):
        return _StubOptions(challenge=b"reg-challenge")

    def gen_auth(**kw):
        return _StubOptions(challenge=b"auth-challenge")

    def verify_reg(credential, expected_challenge, **kw):
        return _RegResult(
            credential_id=_RAW_CRED_ID,
            credential_public_key=b"pubkey-bytes",
            sign_count=0,
            credential_backed_up=True,
        )

    def verify_auth(credential, expected_challenge, credential_current_sign_count, **kw):
        return _AuthResult(new_sign_count=credential_current_sign_count + 1)

    def options_to_json(options):
        return '{"publicKey": {"challenge": "stub", "rp": {"id": "test"}}}'

    # Patch the lazy lib loader so the service uses our doubles.
    fake_lib = types.SimpleNamespace(
        generate_registration_options=gen_reg,
        generate_authentication_options=gen_auth,
        verify_registration_response=verify_reg,
        verify_authentication_response=verify_auth,
        options_to_json=options_to_json,
        helpers=sys.modules["webauthn"].helpers,
    )
    monkeypatch.setattr(svc, "_load_webauthn", lambda: fake_lib)
    return fake_lib


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------
def test_register_begin_returns_publickey_options(client, auth_headers, webauthn_lib):
    r = client.post("/api/v1/webauthn/register/begin", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "publicKey" in body
    assert isinstance(body["publicKey"], dict)


def test_register_finish_persists_credential(client, auth_headers, webauthn_lib, db):
    client.post("/api/v1/webauthn/register/begin", headers=auth_headers)
    r = client.post(
        "/api/v1/webauthn/register/finish",
        headers=auth_headers,
        json={"credential": DUMMY_CREDENTIAL, "nickname": "Test Touch ID"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nickname"] == "Test Touch ID"
    db.expire_all()
    creds = list(db.scalars(select(WebAuthnCredential).where(WebAuthnCredential.id == body["id"])))
    assert len(creds) == 1
    assert creds[0].credential_id == _RAW_CRED_ID
    assert creds[0].public_key == b"pubkey-bytes"
    assert creds[0].backed_up is True


# ---------------------------------------------------------------------------
# Authenticate
# ---------------------------------------------------------------------------
def _register_credential_directly(db, user, *, credential_id=_RAW_CRED_ID, sign_count=0):
    """Insert a WebAuthnCredential bypassing the ceremony."""
    cred = WebAuthnCredential(
        user_id=user.id,
        credential_id=credential_id,
        public_key=b"pubkey",
        sign_count=sign_count,
        backed_up=False,
        transports=["internal"],
        nickname="seed",
    )
    db.add(cred)
    db.flush()
    db.commit()
    return cred


def test_authenticate_begin_then_finish_mints_tokens(client, webauthn_lib, db, session_factory):
    # Seed: register a credential against the default admin user
    admin = db.scalar(select(User).where(User.email == "admin@local"))
    assert admin is not None
    _register_credential_directly(db, admin, credential_id=b"cred-login", sign_count=0)

    begin = client.post(
        "/api/v1/webauthn/authenticate/begin",
        json={"email": "admin@local"},
    )
    assert begin.status_code == 200, begin.text
    assert "publicKey" in begin.json()

    # Build a payload that resolves to credential_id=b"cred-login"
    cred_b64 = base64.urlsafe_b64encode(b"cred-login").rstrip(b"=").decode()
    finish_payload = {
        "email": "admin@local",
        "credential": {
            "id": cred_b64,
            "rawId": cred_b64,
            "type": "public-key",
            "response": {"clientDataJSON": "x", "authenticatorData": "x", "signature": "x"},
        },
    }
    finish = client.post("/api/v1/webauthn/authenticate/finish", json=finish_payload)
    assert finish.status_code == 200, finish.text
    body = finish.json()
    assert "access_token" in body
    assert "refresh_token" in body


def test_authenticate_begin_unknown_email_does_not_enumerate(client, webauthn_lib):
    r = client.post(
        "/api/v1/webauthn/authenticate/begin",
        json={"email": "no-such-user@example.com"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "publicKey" in body


def test_authenticate_finish_wrong_email_returns_401(client, webauthn_lib):
    cred_b64 = base64.urlsafe_b64encode(b"fake").rstrip(b"=").decode()
    r = client.post(
        "/api/v1/webauthn/authenticate/finish",
        json={
            "email": "no-such-user@example.com",
            "credential": {
                "id": cred_b64,
                "rawId": cred_b64,
                "type": "public-key",
                "response": {},
            },
        },
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Sign count replay defense
# ---------------------------------------------------------------------------
def test_authenticate_replay_rejected(client, webauthn_lib, db, monkeypatch):
    import app.services.webauthn as svc

    admin = db.scalar(select(User).where(User.email == "admin@local"))
    cred = _register_credential_directly(db, admin, credential_id=b"cred-replay", sign_count=10)

    # Lib pretends the authenticator advanced to sign_count=10 — equal to
    # what we already have on file. The service should refuse this as a
    # replay.
    def stale_verify(credential, expected_challenge, credential_current_sign_count, **kw):
        return _AuthResult(new_sign_count=10)  # didn't advance

    fake_lib = types.SimpleNamespace(
        generate_registration_options=lambda **k: _StubOptions(b"reg"),
        generate_authentication_options=lambda **k: _StubOptions(b"auth-replay"),
        verify_registration_response=lambda **k: _RegResult(b"x", b"y"),
        verify_authentication_response=stale_verify,
        options_to_json=lambda o: '{"publicKey": {}}',
        helpers=sys.modules["webauthn"].helpers,
    )
    monkeypatch.setattr(svc, "_load_webauthn", lambda: fake_lib)

    client.post("/api/v1/webauthn/authenticate/begin", json={"email": "admin@local"})
    cred_b64 = base64.urlsafe_b64encode(b"cred-replay").rstrip(b"=").decode()
    r = client.post(
        "/api/v1/webauthn/authenticate/finish",
        json={
            "email": "admin@local",
            "credential": {
                "id": cred_b64, "rawId": cred_b64, "type": "public-key",
                "response": {},
            },
        },
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Credential management
# ---------------------------------------------------------------------------
def test_list_and_revoke_credentials(client, auth_headers, webauthn_lib, db, monkeypatch):
    # Re-patch verify_registration_response to return a unique credential_id
    # so this test isn't shadowed by an earlier register_finish row.
    import app.services.webauthn as svc
    base = svc._load_webauthn()
    def verify_reg(credential, expected_challenge, **kw):
        return _RegResult(
            credential_id=b"cred-list-revoke",
            credential_public_key=b"pubkey-bytes",
            sign_count=0,
        )
    fake_lib = types.SimpleNamespace(
        generate_registration_options=base.generate_registration_options,
        generate_authentication_options=base.generate_authentication_options,
        verify_registration_response=verify_reg,
        verify_authentication_response=base.verify_authentication_response,
        options_to_json=base.options_to_json,
        helpers=sys.modules["webauthn"].helpers,
    )
    monkeypatch.setattr(svc, "_load_webauthn", lambda: fake_lib)

    # Register one credential so the list is non-empty.
    client.post("/api/v1/webauthn/register/begin", headers=auth_headers)
    finish = client.post(
        "/api/v1/webauthn/register/finish",
        headers=auth_headers,
        json={"credential": DUMMY_CREDENTIAL, "nickname": "List/Revoke"},
    )
    assert finish.status_code == 200, finish.text
    cred_id = finish.json()["id"]

    listing = client.get("/api/v1/webauthn/credentials", headers=auth_headers)
    assert listing.status_code == 200
    creds = listing.json()["credentials"]
    assert any(c["id"] == cred_id for c in creds)

    rev = client.delete(f"/api/v1/webauthn/credentials/{cred_id}", headers=auth_headers)
    assert rev.status_code == 204

    db.expire_all()
    assert db.get(WebAuthnCredential, cred_id) is None


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------
def test_cross_tenant_credential_does_not_authenticate(
    client, make_tenant, webauthn_lib, session_factory, db,
):
    tenant_a, user_a, _ = make_tenant("wa-a")
    tenant_b, user_b, _ = make_tenant("wa-b")

    # Register a credential under tenant A
    with session_factory() as s, tenant_scope(tenant_a.id):
        cred = WebAuthnCredential(
            user_id=user_a.id,
            credential_id=b"cred-cross-tenant",
            public_key=b"k",
            sign_count=0,
            backed_up=False,
            transports=[],
        )
        s.add(cred)
        s.commit()

    # Try to use it via tenant B's email — should fail
    cred_b64 = base64.urlsafe_b64encode(b"cred-cross-tenant").rstrip(b"=").decode()
    r = client.post(
        "/api/v1/webauthn/authenticate/finish",
        json={
            "email": user_b.email,
            "credential": {
                "id": cred_b64, "rawId": cred_b64, "type": "public-key",
                "response": {},
            },
        },
    )
    assert r.status_code == 401
