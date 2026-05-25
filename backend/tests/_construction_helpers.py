"""Shared helpers for the construction test suite.

Test-only — not imported by app code.
"""
from __future__ import annotations


def set_verticals_plan(monkeypatch):
    """Force the active plan to VERTICALS so construction endpoints respond."""
    from app.core.license_key import LicenseStatus
    stub = LicenseStatus(
        valid=True, state="active", reason="stub",
        customer="acme", plan="verticals",
    )
    monkeypatch.setattr(
        "app.core.license_key.verify_license", lambda: stub,
    )


def make_project(client, auth_headers, **overrides):
    """Create a construction project via the API and return the row dict."""
    payload = {
        "name": "Test Project",
        "client_name": "Acme Corp",
        "location": "Site A",
        "project_type": "commercial",
        "contract_value": "1000000.00",
        "currency": "USD",
        "status": "active",
    }
    payload.update(overrides)
    r = client.post(
        "/api/v1/construction/projects",
        headers=auth_headers,
        json=payload,
    )
    assert r.status_code == 201, r.text
    return r.json()
