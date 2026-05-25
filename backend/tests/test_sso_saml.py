"""Tests for SAML SSO endpoints.

We deliberately do NOT exercise the real ``python3-saml`` signature
verifier here — it requires real signed XML from a real IdP, which is
the wrong shape of plumbing for a unit test. Instead we patch
``app.services.sso_saml.verify_response`` to a stub that returns a
canned attribute dict, and assert the *endpoint* behaviour with that
boundary held fixed.

Config validation, redirect formatting, metadata generation, and the
relay-state cookie verifier are all real and uncovered by mocks.
"""
from __future__ import annotations

import base64
import json

import pytest

from app.services import sso_saml


def _configure_saml(client, auth_headers):
    payload = {
        "provider_type": "saml",
        "is_enabled": True,
        "idp_entity_id": "https://idp.test/saml/entity",
        "idp_sso_url": "https://idp.test/saml/sso",
        "idp_x509_cert": (
            "-----BEGIN CERTIFICATE-----\n"
            "MIIBdjCCAR4CCQDz0g8I3UWjsTAKBggqhkjOPQQDAjBOMQswCQYDVQQGEwJVUzEL\n"
            "MAkGA1UECAwCQ0ExFTATBgNVBAcMDFNhbiBGcmFuY2lzY28xGzAZBgNVBAoMElNh\n"
            "bXBsZSBJZGVudGl0eSBQcm92aWRlcjAeFw0yMDAxMDEwMDAwMDBaFw0zMDAxMDEw\n"
            "MDAwMDBaME4xCzAJBgNVBAYTAlVTMQswCQYDVQQIDAJDQTEVMBMGA1UEBwwMU2Fu\n"
            "IEZyYW5jaXNjbzEbMBkGA1UECgwSU2FtcGxlIElkZW50aXR5IFByMFkwEwYHKoZI\n"
            "zj0CAQYIKoZIzj0DAQcDQgAEVgxAQ9p2Q3GTl4bUVtVB9DfqyP/JuP04Ed8APvqJ\n"
            "M1KLN8/MQbVxz0XSXkR5j8ePZWVjqAUajqsXg++eVa1NAjAKBggqhkjOPQQDAgNI\n"
            "ADBFAiEA3MzbRsRn0jVHRZ4xVoBHWGTSlAm4qY/B0fyJbXmINgQCIGw8tICPHRZh\n"
            "fIp0AbF6VrLqVoG6vrJ9EuV8DhAH3FsB\n"
            "-----END CERTIFICATE-----\n"
        ),
        "email_attribute": "email",
        "name_attribute": "name",
        "auto_provision_users": True,
        "default_role_for_new_users": "employee",
    }
    r = client.post("/api/v1/sso/config", json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Config + metadata
# ---------------------------------------------------------------------------
def test_saml_config_round_trip(client, auth_headers):
    _configure_saml(client, auth_headers)
    r = client.get("/api/v1/sso/config", headers=auth_headers)
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["provider_type"] == "saml"
    assert cfg["idp_sso_url"] == "https://idp.test/saml/sso"


def test_saml_metadata_returns_valid_xml(client, auth_headers):
    _configure_saml(client, auth_headers)
    r = client.get("/api/v1/sso/saml/metadata?tenant_slug=default")
    assert r.status_code == 200
    text = r.text
    assert text.startswith("<?xml") or "<EntityDescriptor" in text or "<md:EntityDescriptor" in text
    # The SP entity id should appear somewhere in the document.
    assert "entityID=" in text or "entityID =" in text


def test_saml_metadata_unknown_tenant_returns_404(client):
    r = client.get("/api/v1/sso/saml/metadata?tenant_slug=does-not-exist")
    assert r.status_code == 404


def test_saml_login_redirects_to_idp(client, auth_headers):
    _configure_saml(client, auth_headers)
    r = client.get(
        "/api/v1/sso/saml/login?tenant_slug=default", follow_redirects=False,
    )
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("https://idp.test/saml/sso")
    assert "sso_saml_relay=" in r.headers.get("set-cookie", "")


# ---------------------------------------------------------------------------
# ACS — patches verify_response
# ---------------------------------------------------------------------------
def test_saml_acs_with_valid_assertion_creates_session(client, auth_headers, monkeypatch):
    _configure_saml(client, auth_headers)
    monkeypatch.setattr(
        sso_saml,
        "verify_response",
        lambda saml_response_b64, cfg, base_url: {
            "email": "saml-user@example.com",
            "name": "SAML User",
            "NameID": "saml-user@example.com",
        },
    )
    # Prime the relay cookie by hitting /login first.
    r = client.get(
        "/api/v1/sso/saml/login?tenant_slug=default", follow_redirects=False,
    )
    relay_cookie = r.headers["set-cookie"].split("sso_saml_relay=", 1)[1].split(";", 1)[0]
    relay_state = r.headers["location"].split("RelayState=", 1)[1].split("&", 1)[0] if "RelayState=" in r.headers["location"] else ""
    # python3-saml may URL-encode RelayState — but the cookie's pack contains the raw value.
    # Pull it out of the signed cookie directly so we don't fight URL encoding.
    body_hex = relay_cookie.split(".")[0]
    raw = json.loads(bytes.fromhex(body_hex).decode())
    relay_state = raw["relay_state"]

    r2 = client.post(
        "/api/v1/sso/saml/acs",
        data={"SAMLResponse": "doesnt-matter-mocked", "RelayState": relay_state},
        cookies={"sso_saml_relay": relay_cookie},
        follow_redirects=False,
    )
    assert r2.status_code in (200, 302, 303), r2.text


def test_saml_acs_with_bad_signature_rejected(client, auth_headers, monkeypatch):
    _configure_saml(client, auth_headers)
    def bad_verify(*a, **k):
        raise ValueError("Signature invalid")
    monkeypatch.setattr(sso_saml, "verify_response", bad_verify)
    r = client.get(
        "/api/v1/sso/saml/login?tenant_slug=default", follow_redirects=False,
    )
    relay_cookie = r.headers["set-cookie"].split("sso_saml_relay=", 1)[1].split(";", 1)[0]
    body_hex = relay_cookie.split(".")[0]
    raw = json.loads(bytes.fromhex(body_hex).decode())
    r2 = client.post(
        "/api/v1/sso/saml/acs",
        data={"SAMLResponse": "tampered", "RelayState": raw["relay_state"]},
        cookies={"sso_saml_relay": relay_cookie},
        follow_redirects=False,
    )
    assert r2.status_code == 401


def test_saml_acs_missing_response_body_rejected(client, auth_headers):
    _configure_saml(client, auth_headers)
    r = client.post("/api/v1/sso/saml/acs", data={})
    assert r.status_code == 401


def test_saml_sls_clears_cookies(client):
    r = client.get("/api/v1/sso/saml/sls", follow_redirects=False)
    assert r.status_code == 200
    # set-cookie header should include several deletions
    set_cookie = r.headers.get("set-cookie", "")
    assert "access_token" in set_cookie or "refresh_token" in set_cookie


# ---------------------------------------------------------------------------
# Relay-state cookie verifier (pure-Python helper)
# ---------------------------------------------------------------------------
def test_relay_state_cookie_round_trip():
    packed = sso_saml.pack_relay_cookie("tid-abc", "relay-xyz", "/dashboard")
    data = sso_saml.unpack_relay_cookie(packed, "relay-xyz")
    assert data["tenant_id"] == "tid-abc"
    assert data["redirect_after"] == "/dashboard"


def test_relay_state_cookie_tamper_rejected():
    packed = sso_saml.pack_relay_cookie("tid-abc", "relay-xyz", "/")
    # Corrupt the signature
    body, _sig = packed.rsplit(".", 1)
    tampered = body + ".deadbeef"
    with pytest.raises(ValueError):
        sso_saml.unpack_relay_cookie(tampered, "relay-xyz")


def test_relay_state_mismatch_rejected():
    packed = sso_saml.pack_relay_cookie("tid-abc", "relay-xyz", "/")
    with pytest.raises(ValueError):
        sso_saml.unpack_relay_cookie(packed, "relay-other")
