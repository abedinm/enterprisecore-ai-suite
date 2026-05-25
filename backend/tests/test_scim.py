"""Tests for SCIM 2.0 + SCIM token mgmt."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.models.sso import SCIMToken
from app.models.user import User


@pytest.fixture()
def scim_token(client, auth_headers):
    """Mint a fresh SCIM token for the default tenant and return the raw value."""
    r = client.post(
        "/api/v1/sso/scim/tokens",
        json={"name": "Okta Test", "ttl_days": 30},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    return body["token"], body["id"]


@pytest.fixture()
def scim_headers(scim_token):
    raw, _ = scim_token
    return {"Authorization": f"Bearer {raw}"}


def test_create_scim_token_returns_raw_once(client, auth_headers):
    r = client.post(
        "/api/v1/sso/scim/tokens",
        json={"name": "Okta Prod", "ttl_days": 365},
        headers=auth_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["token"].startswith("scim_")
    assert body["name"] == "Okta Prod"


def test_list_scim_tokens_omits_raw(client, auth_headers, scim_token):
    r = client.get("/api/v1/sso/scim/tokens", headers=auth_headers)
    assert r.status_code == 200
    rows = r.json()
    assert any(t["name"] == "Okta Test" for t in rows)
    assert all("token" not in t for t in rows)


def test_scim_users_listing(client, scim_headers):
    r = client.get("/scim/v2/Users", headers=scim_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:ListResponse"]
    assert body["totalResults"] >= 1  # The seeded admin
    # Resources have SCIM core schema
    for u in body["Resources"]:
        assert "urn:ietf:params:scim:schemas:core:2.0:User" in u["schemas"]
        assert u["userName"]


def test_scim_create_get_user(client, scim_headers):
    r = client.post(
        "/scim/v2/Users",
        json={
            "userName": "scim-created@example.com",
            "displayName": "Scim Created",
            "active": True,
        },
        headers=scim_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    uid = body["id"]
    assert body["userName"] == "scim-created@example.com"
    # GET back
    r2 = client.get(f"/scim/v2/Users/{uid}", headers=scim_headers)
    assert r2.status_code == 200
    assert r2.json()["userName"] == "scim-created@example.com"


def test_scim_patch_replaces_displayname(client, scim_headers):
    r = client.post(
        "/scim/v2/Users",
        json={"userName": "scim-patch@example.com", "displayName": "Old Name"},
        headers=scim_headers,
    )
    uid = r.json()["id"]
    r2 = client.patch(
        f"/scim/v2/Users/{uid}",
        json={
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "replace", "path": "displayName", "value": "New Name"}],
        },
        headers=scim_headers,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["displayName"] == "New Name"


def test_scim_delete_soft_deletes(client, scim_headers):
    r = client.post(
        "/scim/v2/Users",
        json={"userName": "scim-del@example.com", "displayName": "Delete Me"},
        headers=scim_headers,
    )
    uid = r.json()["id"]
    r2 = client.delete(f"/scim/v2/Users/{uid}", headers=scim_headers)
    assert r2.status_code == 204
    # Soft-deleted — GET returns the user with active=false
    r3 = client.get(f"/scim/v2/Users/{uid}", headers=scim_headers)
    assert r3.status_code == 200
    assert r3.json()["active"] is False


def test_scim_pagination(client, scim_headers):
    # Force ~4 extra users so pagination has something to slice.
    for n in range(4):
        client.post(
            "/scim/v2/Users",
            json={"userName": f"page-{n}@example.com", "displayName": f"Page {n}"},
            headers=scim_headers,
        )
    r = client.get("/scim/v2/Users?startIndex=1&count=2", headers=scim_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["itemsPerPage"] == 2
    assert len(body["Resources"]) == 2
    assert body["totalResults"] >= 5


def test_scim_unauthenticated_request_rejected(client):
    r = client.get("/scim/v2/Users")
    assert r.status_code == 401


def test_scim_revoked_token_rejected(client, auth_headers, scim_token, session_factory):
    raw, token_id = scim_token
    rev = client.delete(f"/api/v1/sso/scim/tokens/{token_id}", headers=auth_headers)
    assert rev.status_code == 204
    r = client.get("/scim/v2/Users", headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 401


def test_scim_cross_tenant_isolation(client, auth_headers, scim_headers, make_tenant):
    """A SCIM token issued for tenant A must NOT see tenant B's users."""
    other, _, other_token = make_tenant("other-scim-co")
    other_auth = {"Authorization": f"Bearer {other_token}"}
    # Make a SCIM token for the OTHER tenant
    rs = client.post(
        "/api/v1/sso/scim/tokens",
        json={"name": "Other SCIM", "ttl_days": 7},
        headers=other_auth,
    )
    other_scim = rs.json()["token"]
    # Create a user in OTHER tenant via SCIM
    client.post(
        "/scim/v2/Users",
        json={"userName": "isolated@other.test"},
        headers={"Authorization": f"Bearer {other_scim}"},
    )
    # Default-tenant SCIM token must not see them
    r = client.get(
        "/scim/v2/Users?filter=userName eq \"isolated@other.test\"",
        headers=scim_headers,
    )
    assert r.status_code == 200
    assert r.json()["totalResults"] == 0
