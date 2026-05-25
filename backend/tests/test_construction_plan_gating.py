"""Plan gating — when 'construction' is not in the active plan, every
construction endpoint returns 403.

We patch both license resolution AND the PLAN_FEATURES dict so this test is
robust against either path.
"""
from __future__ import annotations


API = "/api/v1/construction"


def test_endpoints_403_when_feature_disabled(client, auth_headers, monkeypatch):
    """Strip 'construction' from every plan and confirm the routes are denied."""
    from app.core import plans as plans_mod
    from app.core.license_key import LicenseStatus

    # Force EVALUATION-like plan AND strip 'construction' from every plan's
    # feature set so the gate denies regardless of resolver path.
    stub = LicenseStatus(
        valid=False, state="evaluation", reason="stub",
        customer="acme", plan=None,
    )
    monkeypatch.setattr("app.core.license_key.verify_license", lambda: stub)

    patched = {plan: set(feats) for plan, feats in plans_mod.PLAN_FEATURES.items()}
    for feats in patched.values():
        feats.discard("construction")
    monkeypatch.setattr(plans_mod, "PLAN_FEATURES", patched)

    r = client.get(f"{API}/projects", headers=auth_headers)
    assert r.status_code == 403, r.text
    assert r.json().get("code") == "permission_denied"

    r2 = client.post(
        f"{API}/projects",
        headers=auth_headers,
        json={
            "name": "Blocked", "project_type": "residential",
            "contract_value": "100.00", "currency": "USD",
        },
    )
    assert r2.status_code == 403


def test_endpoints_200_under_verticals_plan(client, auth_headers, monkeypatch):
    """Sanity: with the VERTICALS plan the route responds normally."""
    from app.core.license_key import LicenseStatus
    stub = LicenseStatus(
        valid=True, state="active", reason="stub",
        customer="acme", plan="verticals",
    )
    monkeypatch.setattr("app.core.license_key.verify_license", lambda: stub)
    r = client.get(f"{API}/projects", headers=auth_headers)
    assert r.status_code == 200, r.text


def test_endpoints_200_under_edu_plan(client, auth_headers, monkeypatch):
    """EDU customers also get construction (universities run building projects)."""
    from app.core.license_key import LicenseStatus
    stub = LicenseStatus(
        valid=True, state="active", reason="stub",
        customer="uni", plan="edu",
    )
    monkeypatch.setattr("app.core.license_key.verify_license", lambda: stub)
    r = client.get(f"{API}/projects", headers=auth_headers)
    assert r.status_code == 200


def test_core_plan_does_not_unlock_construction(client, auth_headers, monkeypatch):
    """CORE customers don't get construction unless they upgrade to VERTICALS."""
    from app.core.license_key import LicenseStatus
    stub = LicenseStatus(
        valid=True, state="active", reason="stub",
        customer="core-co", plan="core",
    )
    monkeypatch.setattr("app.core.license_key.verify_license", lambda: stub)
    r = client.get(f"{API}/projects", headers=auth_headers)
    assert r.status_code == 403


def test_module_catalog_includes_construction_under_verticals(
    client, auth_headers, monkeypatch,
):
    from app.core.license_key import LicenseStatus
    stub = LicenseStatus(
        valid=True, state="active", reason="stub",
        customer="acme", plan="verticals",
    )
    monkeypatch.setattr("app.core.license_key.verify_license", lambda: stub)
    r = client.get("/api/v1/modules", headers=auth_headers)
    assert r.status_code == 200
    groups = [g["group"] for g in r.json()["groups"]]
    assert "Construction" in groups
