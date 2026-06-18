"""/api/v1/modules and /api/v1/license/features filter behaviour."""
from __future__ import annotations


def _set_plan(monkeypatch, plan: str | None, state: str = "active"):
    from app.core.license_key import LicenseStatus
    stub = LicenseStatus(
        valid=(state == "active"),
        state=state,
        reason="stub",
        customer="acme",
        plan=plan,
    )
    monkeypatch.setattr("app.core.license_key.verify_license", lambda: stub)


def test_modules_evaluation_includes_webchat_and_marketing_not_academic(
    client, auth_headers, monkeypatch, reset_response_cache
):
    _set_plan(monkeypatch, plan=None, state="evaluation")
    r = client.get("/api/v1/modules", headers=auth_headers)
    assert r.status_code == 200
    groups = [g["group"] for g in r.json()["groups"]]
    assert "Web Chat" in groups
    assert "Marketing" in groups
    assert "Academic" not in groups
    # Always-on platform modules still present
    assert "Finance" in groups
    assert "CRM" in groups


def test_modules_edu_includes_academic(client, auth_headers, monkeypatch, reset_response_cache):
    _set_plan(monkeypatch, plan="edu")
    r = client.get("/api/v1/modules", headers=auth_headers)
    assert r.status_code == 200
    groups = [g["group"] for g in r.json()["groups"]]
    assert "Academic" in groups
    assert "Web Chat" in groups


def test_modules_core_excludes_academic(client, auth_headers, monkeypatch, reset_response_cache):
    _set_plan(monkeypatch, plan="core")
    r = client.get("/api/v1/modules", headers=auth_headers)
    assert r.status_code == 200
    groups = [g["group"] for g in r.json()["groups"]]
    assert "Academic" not in groups
    assert "Web Chat" in groups
    assert "Marketing" in groups


def test_license_features_endpoint_returns_plan_and_features(
    client, auth_headers, monkeypatch, reset_response_cache
):
    _set_plan(monkeypatch, plan="edu")
    r = client.get("/api/v1/license/features", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "edu"
    assert "academic" in body["features"]
    assert "webchat" in body["features"]
    assert "marketing" in body["features"]


def test_license_features_endpoint_requires_auth(client):
    client.cookies.clear()
    r = client.get("/api/v1/license/features")
    assert r.status_code == 401
