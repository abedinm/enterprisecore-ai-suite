"""Tenant lifecycle endpoints — signup, invite, accept, usage, RBAC."""
from __future__ import annotations

from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.models.tenant import Tenant, TenantInvite
from app.models.user import User


def test_signup_creates_tenant_and_admin_user(client):
    payload = {
        "name": "Acme Industries",
        "slug": "acme-industries",
        "admin_email": "founder@acme.test",
        "admin_password": "AcmePass123!",
        "admin_full_name": "Wile E Coyote",
        "primary_contact_email": "ops@acme.test",
    }
    r = client.post("/api/v1/tenants/signup", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["tenant"]["slug"] == "acme-industries"
    assert body["tenant"]["plan"] == "evaluation"
    assert body["access_token"]
    # The new admin can immediately use the token.
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "founder@acme.test"


def test_signup_with_duplicate_slug_returns_409(client):
    base = {
        "name": "Slug Collision Co",
        "slug": "slugfest",
        "admin_email": "first@slugfest.test",
        "admin_password": "FirstPass99!",
        "admin_full_name": "First Founder",
    }
    r1 = client.post("/api/v1/tenants/signup", json=base)
    assert r1.status_code == 201, r1.text

    payload2 = dict(base, admin_email="second@slugfest.test")
    r2 = client.post("/api/v1/tenants/signup", json=payload2)
    assert r2.status_code == 409, r2.text


def test_signup_rejects_weak_password(client):
    payload = {
        "name": "Weak Pass Co",
        "slug": "weakpass-co",
        "admin_email": "weak@example.test",
        "admin_password": "short",
        "admin_full_name": "Test Founder",
    }
    r = client.post("/api/v1/tenants/signup", json=payload)
    # Pydantic validation rejects the short password before the handler runs.
    assert r.status_code == 422


def test_signup_rejects_invalid_slug(client):
    payload = {
        "name": "Bad Slug Co",
        "slug": "Bad SLUG with spaces",
        "admin_email": "x@y.test",
        "admin_password": "GoodPass123!",
        "admin_full_name": "Founder",
    }
    r = client.post("/api/v1/tenants/signup", json=payload)
    assert r.status_code == 422


def test_get_me_returns_current_tenant(client, auth_headers):
    r = client.get("/api/v1/tenants/me", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["slug"] == "default"


def test_patch_me_updates_tenant(client, auth_headers):
    r = client.patch(
        "/api/v1/tenants/me",
        json={"name": "Renamed Tenant", "timezone": "Europe/London"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed Tenant"
    assert r.json()["timezone"] == "Europe/London"


def test_invite_requires_admin(client):
    # Spin up a non-admin user via /tenants/signup so we have a fresh tenant
    # with an employee account.
    sig = {
        "name": "Permission Co",
        "slug": "permissions-co",
        "admin_email": "boss@permissions.test",
        "admin_password": "BossPass77!",
        "admin_full_name": "Boss",
    }
    r = client.post("/api/v1/tenants/signup", json=sig)
    assert r.status_code == 201
    # Register an employee via the legacy endpoint in the *default* tenant —
    # cross-tenant impersonation should be impossible regardless.
    emp_login = client.post(
        "/api/v1/auth/register",
        json={"email": "emp@perm.test", "full_name": "Emp", "password": "EmpPass123!"},
    )
    assert emp_login.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "emp@perm.test", "password": "EmpPass123!"},
    ).json()
    invite_r = client.post(
        "/api/v1/tenants/me/users/invite",
        json={"email": "anyone@example.test", "role": "Employee"},
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )
    assert invite_r.status_code == 403


def test_invite_creates_pending_row(client, auth_headers, session_factory):
    r = client.post(
        "/api/v1/tenants/me/users/invite",
        json={"email": "newbie@inv.test", "role": "Employee"},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "newbie@inv.test"
    assert body["status"] == "pending"
    assert body["token"]


def test_accept_invite_creates_user_under_target_tenant(client, auth_headers):
    inv = client.post(
        "/api/v1/tenants/me/users/invite",
        json={"email": "accept@inv.test", "role": "Employee"},
        headers=auth_headers,
    ).json()
    token = inv["token"]

    r = client.post(
        "/api/v1/tenants/accept-invite",
        json={"token": token, "password": "GoodPass99!", "full_name": "Invitee"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["access_token"]
    # The new user can log in with the new password.
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "accept@inv.test", "password": "GoodPass99!"},
    )
    assert login.status_code == 200


def test_accept_invite_with_bad_token_returns_404(client):
    r = client.post(
        "/api/v1/tenants/accept-invite",
        json={"token": "this-token-does-not-exist", "password": "WhatPass123!", "full_name": "Nobody"},
    )
    assert r.status_code == 404


def test_accept_invite_twice_returns_410(client, auth_headers):
    inv = client.post(
        "/api/v1/tenants/me/users/invite",
        json={"email": "twice@inv.test", "role": "Employee"},
        headers=auth_headers,
    ).json()
    token = inv["token"]
    client.post(
        "/api/v1/tenants/accept-invite",
        json={"token": token, "password": "FirstPass99!", "full_name": "First Use"},
    )
    r2 = client.post(
        "/api/v1/tenants/accept-invite",
        json={"token": token, "password": "SecondPass99!", "full_name": "Second Use"},
    )
    assert r2.status_code == 410


def test_usage_endpoint_returns_counts(client, auth_headers):
    r = client.get("/api/v1/tenants/me/usage", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_count"] >= 1  # at least the admin
    # storage_mb is now real accounting (was a 0.0 stub before). It may be
    # 0.0 for a brand-new tenant or non-zero if seed/prior tests have left
    # rows behind — either way it must be a finite non-negative number.
    assert isinstance(body["storage_mb"], (float, int))
    assert body["storage_mb"] >= 0.0
    assert body["ai_spend_ytd_usd"] >= 0.0
