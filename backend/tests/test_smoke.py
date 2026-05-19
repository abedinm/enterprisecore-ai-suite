"""Quick end-to-end smoke test — verifies the foundation works."""
from __future__ import annotations


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db_backend"] == "sqlite"


def test_login_and_me(client):
    login = client.post("/api/v1/auth/login", json={"email": "admin@local", "password": "ChangeMe123!"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["email"] == "admin@local"
    assert body["role"] == "Admin"


def test_wrong_password_rejected(client):
    r = client.post("/api/v1/auth/login", json={"email": "admin@local", "password": "wrong"})
    assert r.status_code == 401


def test_unauthenticated_endpoint_returns_401(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_openapi_includes_finance_routes(client, auth_headers):
    r = client.get("/api/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert any(p.startswith("/api/v1/finance/invoices") for p in paths)
    assert any(p.startswith("/api/v1/coding") for p in paths)
    assert any(p.startswith("/api/v1/ai/") for p in paths)
