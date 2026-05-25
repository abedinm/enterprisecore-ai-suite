"""Salesforce REST API importer tests.

The Salesforce REST API is mocked at the httpx-transport level (via
``httpx.MockTransport``) so the importer is exercised end-to-end without
touching the network. The lib calls under test live in
:mod:`app.services.importers.salesforce_rest`.
"""
from __future__ import annotations

import httpx
from sqlalchemy import select

from app.core.tenant_context import tenant_scope
from app.models.crm import Contact
from app.services.importers import salesforce_rest


SF_INSTANCE = "https://example.my.salesforce.com"


def _mock_httpx(monkeypatch, handler):
    """Patch httpx.post + httpx.get to dispatch through ``handler``.

    ``handler(method, url, params, data, headers)`` should return an
    ``httpx.Response``. Lets each test script its own Salesforce API
    behaviour without standing up a fake server.
    """
    def post(url, *, data=None, headers=None, timeout=None, **kw):
        return handler("POST", url, kw.get("params"), data, headers)

    def get(url, *, params=None, headers=None, timeout=None, **kw):
        return handler("GET", url, params, None, headers)

    monkeypatch.setattr("app.services.importers.salesforce_rest.httpx.post", post)
    monkeypatch.setattr("app.services.importers.salesforce_rest.httpx.get", get)


def _json_response(payload, status=200):
    return httpx.Response(status_code=status, json=payload)


# ---------------------------------------------------------------------------
# OAuth refresh
# ---------------------------------------------------------------------------
def test_sf_rest_oauth_refresh_works(monkeypatch):
    seen = {}

    def handler(method, url, params, data, headers):
        seen["method"] = method
        seen["url"] = url
        seen["data"] = data
        return _json_response({"access_token": "new-access-token", "instance_url": SF_INSTANCE})

    _mock_httpx(monkeypatch, handler)
    token = salesforce_rest.mint_access_token(
        SF_INSTANCE, "refresh-1",
        client_id="cid", client_secret="csecret",
    )
    assert token == "new-access-token"
    assert seen["method"] == "POST"
    assert seen["url"].endswith("/services/oauth2/token")
    assert seen["data"]["grant_type"] == "refresh_token"
    assert seen["data"]["refresh_token"] == "refresh-1"


def test_sf_rest_bad_credentials_raise_401(client, auth_headers, monkeypatch):
    def handler(method, url, params, data, headers):
        if "oauth2/token" in url:
            return _json_response({"error": "invalid_grant"}, status=400)
        return _json_response({}, status=401)

    _mock_httpx(monkeypatch, handler)
    r = client.post(
        "/api/v1/importers/jobs/api",
        headers=auth_headers,
        json={
            "source": "salesforce",
            "target_entity": "contact",
            "source_credentials": {
                "instance_url": SF_INSTANCE,
                "refresh_token": "bad-refresh",
                "client_id": "cid",
                "client_secret": "csecret",
            },
        },
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    commit = client.post(f"/api/v1/importers/jobs/{job_id}/commit", headers=auth_headers)
    assert commit.status_code == 401
    assert "credentials" in commit.json().get("detail", "").lower()


# ---------------------------------------------------------------------------
# Query + pagination
# ---------------------------------------------------------------------------
THREE_CONTACTS = {
    "totalSize": 3,
    "done": True,
    "records": [
        {"attributes": {"type": "Contact"}, "Id": "003a", "FirstName": "Ada", "LastName": "Lovelace", "Email": "ada@example.com", "Phone": "555-0001", "Account": {"attributes": {}, "Name": "Analytical Engines"}},
        {"attributes": {"type": "Contact"}, "Id": "003b", "FirstName": "Grace", "LastName": "Hopper", "Email": "grace@example.com", "Phone": "555-0002", "Account": {"attributes": {}, "Name": "Cobol Co"}},
        {"attributes": {"type": "Contact"}, "Id": "003c", "FirstName": "Linus", "LastName": "Torvalds", "Email": "linus@example.com", "Phone": "555-0003", "Account": {"attributes": {}, "Name": "Linux Foundation"}},
    ],
}


def test_sf_rest_query_returns_three_contacts(client, auth_headers, monkeypatch, db):
    def handler(method, url, params, data, headers):
        return _json_response(THREE_CONTACTS)

    _mock_httpx(monkeypatch, handler)
    r = client.post(
        "/api/v1/importers/jobs/api",
        headers=auth_headers,
        json={
            "source": "salesforce",
            "target_entity": "contact",
            "source_credentials": {
                "instance_url": SF_INSTANCE,
                "access_token": "token-1",
            },
        },
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]

    sm = client.post(
        f"/api/v1/importers/jobs/{job_id}/suggest-mapping", headers=auth_headers,
    )
    assert sm.status_code == 200
    mapping = sm.json()["mapping"]
    assert "firstname" in mapping
    assert mapping["firstname"] == "first_name"
    assert mapping["lastname"] == "last_name"
    assert mapping["email"] == "email"

    client.patch(
        f"/api/v1/importers/jobs/{job_id}/mapping",
        headers=auth_headers,
        json={"column_mapping": mapping},
    )

    commit = client.post(f"/api/v1/importers/jobs/{job_id}/commit", headers=auth_headers)
    assert commit.status_code == 200, commit.text
    body = commit.json()
    assert body["row_count_total"] == 3
    assert body["row_count_imported"] >= 3 - body["row_count_skipped"]
    db.expire_all()
    emails = {c.email for c in db.scalars(
        select(Contact).where(Contact.email.in_(["ada@example.com", "grace@example.com", "linus@example.com"]))
    )}
    assert emails == {"ada@example.com", "grace@example.com", "linus@example.com"}


def test_sf_rest_pagination_via_next_records_url(monkeypatch):
    page1 = {
        "totalSize": 5,
        "done": False,
        "nextRecordsUrl": "/services/data/v60.0/query/01g000000000000-2000",
        "records": [
            {"attributes": {}, "Id": f"c{i}", "FirstName": f"F{i}", "LastName": f"L{i}"} for i in range(3)
        ],
    }
    page2 = {
        "totalSize": 5,
        "done": True,
        "records": [
            {"attributes": {}, "Id": f"c{i}", "FirstName": f"F{i}", "LastName": f"L{i}"} for i in range(3, 5)
        ],
    }
    pages = iter([page1, page2])

    def handler(method, url, params, data, headers):
        return _json_response(next(pages))

    _mock_httpx(monkeypatch, handler)
    client = salesforce_rest.SalesforceRestClient(SF_INSTANCE, "tok")
    records = list(client.query("SELECT Id FROM Contact"))
    assert len(records) == 5
    assert [r["Id"] for r in records] == ["c0", "c1", "c2", "c3", "c4"]


def test_sf_rest_100k_cap_enforced(monkeypatch):
    """The query iterator stops at the configured max_records."""
    def make_page(start, count, done=False):
        return {
            "done": done,
            "nextRecordsUrl": f"/services/data/v60.0/query/{start + count}",
            "records": [{"attributes": {}, "Id": f"i{start + i}"} for i in range(count)],
        }

    # Each page returns 10 — we cap at 25, so iterator should stop after 3 pages.
    pages = iter([
        make_page(0, 10, done=False),
        make_page(10, 10, done=False),
        make_page(20, 10, done=False),
        make_page(30, 10, done=True),  # never reached
    ])

    def handler(method, url, params, data, headers):
        return _json_response(next(pages))

    _mock_httpx(monkeypatch, handler)
    client = salesforce_rest.SalesforceRestClient(SF_INSTANCE, "tok")
    records = list(client.query("SELECT Id FROM Contact", max_records=25))
    assert len(records) == 25


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------
def test_sf_rest_cross_tenant_isolation(
    client, make_tenant, monkeypatch, session_factory,
):
    tenant_a, _, token_a = make_tenant("sfrest-a")
    tenant_b, _, token_b = make_tenant("sfrest-b")

    payload = {
        "totalSize": 1,
        "done": True,
        "records": [
            {
                "attributes": {},
                "Id": "003iso",
                "FirstName": "Iso",
                "LastName": "Tenant",
                "Email": "iso@tenant-a.example",
            },
        ],
    }

    def handler(method, url, params, data, headers):
        return _json_response(payload)

    _mock_httpx(monkeypatch, handler)

    headers_a = {"Authorization": f"Bearer {token_a}"}
    r = client.post(
        "/api/v1/importers/jobs/api",
        headers=headers_a,
        json={
            "source": "salesforce",
            "target_entity": "contact",
            "source_credentials": {"instance_url": SF_INSTANCE, "access_token": "t"},
        },
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    sm = client.post(
        f"/api/v1/importers/jobs/{job_id}/suggest-mapping", headers=headers_a,
    ).json()["mapping"]
    client.patch(
        f"/api/v1/importers/jobs/{job_id}/mapping",
        headers=headers_a,
        json={"column_mapping": sm},
    )
    client.post(f"/api/v1/importers/jobs/{job_id}/commit", headers=headers_a)

    with session_factory() as s, tenant_scope(tenant_b.id):
        rows = list(s.scalars(
            select(Contact).where(Contact.email == "iso@tenant-a.example")
        ))
        assert rows == []
    with session_factory() as s, tenant_scope(tenant_a.id):
        rows = list(s.scalars(
            select(Contact).where(Contact.email == "iso@tenant-a.example")
        ))
        assert len(rows) == 1
