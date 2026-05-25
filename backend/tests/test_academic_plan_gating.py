"""Plan gating — when 'academic' is not in the active plan, every academic
endpoint returns 403.

We patch both license resolution AND the PLAN_FEATURES dict so this test is
robust against either path.
"""
from __future__ import annotations


API = "/api/v1/academic"


def test_endpoints_403_when_feature_disabled(client, auth_headers, monkeypatch):
    """Default test plan is EVALUATION, which doesn't include 'academic', so
    every academic endpoint should already be 403. Verify a representative
    sample explicitly."""
    from app.core import plans as plans_mod

    # Belt-and-braces — also strip 'academic' from every plan's feature set
    # so even if the licence resolver is monkeypatched elsewhere the route
    # stays denied.
    patched = {plan: set(feats) for plan, feats in plans_mod.PLAN_FEATURES.items()}
    for feats in patched.values():
        feats.discard("academic")
    monkeypatch.setattr(plans_mod, "PLAN_FEATURES", patched)

    # Authenticated GET on a known route
    r = client.get(f"{API}/semesters", headers=auth_headers)
    assert r.status_code == 403, r.text
    assert r.json().get("code") == "permission_denied"

    # POST on a writeable route
    r2 = client.post(
        f"{API}/rooms", headers=auth_headers,
        json={"name": "Should not work", "capacity": 10},
    )
    assert r2.status_code == 403

    # Student-only read route also gated
    r3 = client.get(f"{API}/students/me/attendance", headers=auth_headers)
    assert r3.status_code == 403


def test_endpoints_200_when_feature_enabled(client, auth_headers, monkeypatch):
    """Sanity: with the feature enabled, the same routes don't return 403.

    Uses the same EDU-plan stub the other tests use.
    """
    from app.core.license_key import LicenseStatus
    stub = LicenseStatus(
        valid=True, state="active", reason="stub",
        customer="acme", plan="edu",
    )
    monkeypatch.setattr("app.core.license_key.verify_license", lambda: stub)

    r = client.get(f"{API}/semesters", headers=auth_headers)
    assert r.status_code == 200, r.text
