"""Security & compliance module tests."""
from __future__ import annotations


def test_password_vault_encrypt_decrypt(client, auth_headers):
    create = client.post("/api/v1/security/vault", headers=auth_headers, json={
        "title": "GitHub PAT", "username": "abedinm",
        "password": "super-secret-xyz", "notes": "scope: repo",
    })
    assert create.status_code == 200, create.text
    vid = create.json()["id"]

    # List should not include the password
    listing = client.get("/api/v1/security/vault", headers=auth_headers).json()
    entry = next(e for e in listing if e["id"] == vid)
    assert "password" not in entry  # only revealed via /reveal

    # Reveal should round-trip the encryption
    reveal = client.get(f"/api/v1/security/vault/{vid}/reveal", headers=auth_headers)
    assert reveal.status_code == 200
    body = reveal.json()
    assert body["password"] == "super-secret-xyz"
    assert body["notes"] == "scope: repo"


def test_login_attempts_logged(client, auth_headers):
    # Generate a failed attempt
    client.post("/api/v1/auth/login", json={"email": "admin@local", "password": "wrong"})
    summary = client.get("/api/v1/security/login-attempts/summary", headers=auth_headers)
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["total"] >= 1
    assert body["failure"] >= 1


def test_gdpr_checklist(client, auth_headers):
    r = client.get("/api/v1/security/gdpr/checklist", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["framework"] == "GDPR"
    assert len(body["items"]) >= 10


def test_compliance_check_lifecycle(client, auth_headers):
    add = client.post("/api/v1/security/compliance", headers=auth_headers, json={
        "framework": "SOC2", "item": "Quarterly access review", "status": "open",
    })
    assert add.status_code == 200
    cid = add.json()["id"]
    upd = client.post(f"/api/v1/security/compliance/{cid}/status",
                      headers=auth_headers, json={"status": "met", "evidence": "Reviewed 2026-Q1"})
    assert upd.status_code == 200
    assert upd.json()["status"] == "met"
    rep = client.get("/api/v1/security/compliance/report/SOC2", headers=auth_headers)
    assert rep.status_code == 200
    assert rep.json()["met"] >= 1
