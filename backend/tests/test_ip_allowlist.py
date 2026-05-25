"""Tests for the IP allowlist middleware."""
from __future__ import annotations

from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter
from app.models.security_hardening import TenantSecurityPolicy


def _set_policy(db, tenant_id: str, cidrs: list[str], enforced: bool):
    """Idempotent helper: create-or-update the tenant's security policy."""
    with bypass_tenant_filter():
        policy = db.scalar(
            select(TenantSecurityPolicy).where(TenantSecurityPolicy.tenant_id == tenant_id)
        )
        if not policy:
            policy = TenantSecurityPolicy(
                tenant_id=tenant_id,
                ip_allowlist_cidrs=cidrs,
                ip_allowlist_enforced=enforced,
            )
            db.add(policy)
        else:
            policy.ip_allowlist_cidrs = cidrs
            policy.ip_allowlist_enforced = enforced
        db.commit()


def test_empty_allowlist_no_enforcement(client, auth_headers, session_factory, default_tenant):
    with session_factory() as db:
        _set_policy(db, default_tenant.id, [], enforced=False)
    resp = client.get("/api/v1/dashboard/summary", headers=auth_headers)
    # Either 200, 404, or 200-style; the point is NOT 403.
    assert resp.status_code != 403


def test_in_range_ip_allowed(client, auth_headers, session_factory, default_tenant):
    with session_factory() as db:
        _set_policy(db, default_tenant.id, ["127.0.0.0/8"], enforced=True)
    # TestClient uses 127.0.0.1 by default, but we also supply an X-Forwarded-For
    # so the test is deterministic regardless of how starlette reports client.
    headers = dict(auth_headers, **{"X-Forwarded-For": "127.0.0.99"})
    resp = client.get("/api/v1/dashboard/summary", headers=headers)
    assert resp.status_code != 403
    # Cleanup so other tests aren't affected.
    with session_factory() as db:
        _set_policy(db, default_tenant.id, [], enforced=False)


def test_out_of_range_ip_blocked(client, auth_headers, session_factory, default_tenant):
    with session_factory() as db:
        _set_policy(db, default_tenant.id, ["10.0.0.0/8"], enforced=True)
    headers = dict(auth_headers, **{"X-Forwarded-For": "203.0.113.1"})
    resp = client.get("/api/v1/dashboard/summary", headers=headers)
    assert resp.status_code == 403
    # Cleanup.
    with session_factory() as db:
        _set_policy(db, default_tenant.id, [], enforced=False)


def test_x_forwarded_for_leftmost_used(client, auth_headers, session_factory, default_tenant):
    """When X-Forwarded-For has multiple entries, the LEFTMOST is the real
    client. If it's in-range we should pass, even when the socket IP isn't."""
    with session_factory() as db:
        _set_policy(db, default_tenant.id, ["8.8.8.0/24"], enforced=True)
    headers = dict(auth_headers, **{"X-Forwarded-For": "8.8.8.8, 10.0.0.1, 192.168.1.1"})
    resp = client.get("/api/v1/dashboard/summary", headers=headers)
    assert resp.status_code != 403
    with session_factory() as db:
        _set_policy(db, default_tenant.id, [], enforced=False)


def test_public_endpoints_bypass_allowlist(client, session_factory, default_tenant):
    """/api/health and similar public endpoints must never be IP-gated."""
    with session_factory() as db:
        _set_policy(db, default_tenant.id, ["10.255.255.0/24"], enforced=True)
    # Even from a non-matching IP, the health endpoint must respond.
    headers = {"X-Forwarded-For": "203.0.113.99"}
    resp = client.get("/api/health", headers=headers)
    assert resp.status_code == 200
    # Same for the auth login endpoint (so locked-out admins can sign in).
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local", "password": "wrong"},
        headers=headers,
    )
    assert resp.status_code != 403  # 401 is expected for wrong password
    with session_factory() as db:
        _set_policy(db, default_tenant.id, [], enforced=False)


def test_disabled_policy_skips_enforcement(client, auth_headers, session_factory, default_tenant):
    """ip_allowlist_enforced=False short-circuits the middleware even when
    CIDRs are set."""
    with session_factory() as db:
        _set_policy(db, default_tenant.id, ["10.0.0.0/8"], enforced=False)
    headers = dict(auth_headers, **{"X-Forwarded-For": "203.0.113.1"})
    resp = client.get("/api/v1/dashboard/summary", headers=headers)
    assert resp.status_code != 403
    with session_factory() as db:
        _set_policy(db, default_tenant.id, [], enforced=False)


def test_update_ip_allowlist_endpoint(client, auth_headers, session_factory, default_tenant):
    resp = client.put(
        "/api/v1/security/policies/ip-allowlist",
        headers=auth_headers,
        json={"cidrs": ["192.168.0.0/16", "10.0.0.0/8"], "enforced": False},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ip_allowlist_cidrs"] == ["192.168.0.0/16", "10.0.0.0/8"]
    assert data["ip_allowlist_enforced"] is False


def test_invalid_cidr_rejected(client, auth_headers):
    resp = client.put(
        "/api/v1/security/policies/ip-allowlist",
        headers=auth_headers,
        json={"cidrs": ["not-a-cidr"], "enforced": False},
    )
    assert resp.status_code in (400, 422)
