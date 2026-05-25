"""QuickBooks Online API importer tests.

QBO is mocked at the httpx level — same pattern as the Salesforce REST
tests. The importer under test lives in
:mod:`app.services.importers.quickbooks_online`.
"""
from __future__ import annotations

import httpx
from sqlalchemy import select

from app.core.tenant_context import tenant_scope
from app.models.finance import Customer, Invoice
from app.services.importers import quickbooks_online


REALM = "1234567890"


def _mock_httpx(monkeypatch, handler):
    def post(url, *, data=None, headers=None, timeout=None, **kw):
        return handler("POST", url, kw.get("params"), data, headers)

    def get(url, *, params=None, headers=None, timeout=None, **kw):
        return handler("GET", url, params, None, headers)

    monkeypatch.setattr("app.services.importers.quickbooks_online.httpx.post", post)
    monkeypatch.setattr("app.services.importers.quickbooks_online.httpx.get", get)


def _resp(payload, status=200):
    return httpx.Response(status_code=status, json=payload)


# ---------------------------------------------------------------------------
# OAuth refresh
# ---------------------------------------------------------------------------
def test_qbo_oauth_refresh_works(monkeypatch):
    seen = {}

    def handler(method, url, params, data, headers):
        seen["url"] = url
        seen["data"] = data
        return _resp({"access_token": "qbo-access", "refresh_token": "qbo-refresh"})

    _mock_httpx(monkeypatch, handler)
    token = quickbooks_online.mint_access_token(
        "qbo-refresh-1", client_id="cid", client_secret="csec",
    )
    assert token == "qbo-access"
    assert seen["url"].endswith("/tokens/bearer")
    assert seen["data"]["grant_type"] == "refresh_token"


def test_qbo_bad_credentials_raise_401(client, auth_headers, monkeypatch):
    def handler(method, url, params, data, headers):
        if "tokens/bearer" in url:
            return _resp({"error": "invalid_grant"}, status=400)
        return _resp({}, status=401)

    _mock_httpx(monkeypatch, handler)
    r = client.post(
        "/api/v1/importers/jobs/api",
        headers=auth_headers,
        json={
            "source": "quickbooks",
            "target_entity": "customer",
            "source_credentials": {
                "realm_id": REALM,
                "refresh_token": "bad",
                "client_id": "cid",
                "client_secret": "csec",
            },
        },
    )
    assert r.status_code == 201, r.text
    commit = client.post(f"/api/v1/importers/jobs/{r.json()['id']}/commit", headers=auth_headers)
    assert commit.status_code == 401


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------
THREE_CUSTOMERS = {
    "QueryResponse": {
        "Customer": [
            {"Id": "1", "DisplayName": "Acme QBO Customer", "PrimaryEmailAddr": {"Address": "billing@acme.qbo"}},
            {"Id": "2", "DisplayName": "Globex QBO Customer", "PrimaryEmailAddr": {"Address": "ar@globex.qbo"}},
            {"Id": "3", "DisplayName": "Initech QBO Customer", "PrimaryEmailAddr": {"Address": "ap@initech.qbo"}},
        ],
        "startPosition": 1,
        "maxResults": 3,
    },
    "time": "2026-05-23T10:00:00Z",
}


def test_qbo_query_returns_three_customers(client, auth_headers, monkeypatch, db):
    def handler(method, url, params, data, headers):
        return _resp(THREE_CUSTOMERS)

    _mock_httpx(monkeypatch, handler)
    r = client.post(
        "/api/v1/importers/jobs/api",
        headers=auth_headers,
        json={
            "source": "quickbooks",
            "target_entity": "customer",
            "source_credentials": {"realm_id": REALM, "access_token": "tok"},
        },
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    sm = client.post(
        f"/api/v1/importers/jobs/{job_id}/suggest-mapping", headers=auth_headers,
    ).json()["mapping"]
    assert "displayname" in sm or "primaryemailaddr_address" in sm
    client.patch(
        f"/api/v1/importers/jobs/{job_id}/mapping",
        headers=auth_headers,
        json={"column_mapping": sm},
    )
    commit = client.post(f"/api/v1/importers/jobs/{job_id}/commit", headers=auth_headers)
    assert commit.status_code == 200, commit.text
    assert commit.json()["row_count_total"] == 3
    db.expire_all()
    names = {c.name for c in db.scalars(
        select(Customer).where(Customer.name.in_(
            ["Acme QBO Customer", "Globex QBO Customer", "Initech QBO Customer"]
        ))
    )}
    assert names == {"Acme QBO Customer", "Globex QBO Customer", "Initech QBO Customer"}


def test_qbo_pagination_via_startposition(monkeypatch):
    """QBO returns 500-row pages — we ask for it, then ask again."""
    page1_records = [{"Id": str(i), "DisplayName": f"C{i}"} for i in range(quickbooks_online.PAGE_SIZE)]
    page2_records = [{"Id": str(i + 500), "DisplayName": f"C{i + 500}"} for i in range(3)]
    pages = iter([
        {"QueryResponse": {"Customer": page1_records}},
        {"QueryResponse": {"Customer": page2_records}},
    ])

    def handler(method, url, params, data, headers):
        return _resp(next(pages))

    _mock_httpx(monkeypatch, handler)
    c = quickbooks_online.QboClient(REALM, "tok")
    out = list(c.query("Customer"))
    assert len(out) == quickbooks_online.PAGE_SIZE + 3


def test_qbo_100k_cap_enforced(monkeypatch):
    """Iterator stops at max_records even when QBO has more."""
    page = {"QueryResponse": {"Customer": [
        {"Id": str(i), "DisplayName": f"C{i}"} for i in range(quickbooks_online.PAGE_SIZE)
    ]}}

    def handler(method, url, params, data, headers):
        return _resp(page)

    _mock_httpx(monkeypatch, handler)
    c = quickbooks_online.QboClient(REALM, "tok")
    out = list(c.query("Customer", max_records=42))
    assert len(out) == 42


def test_qbo_invoice_commit_with_total(client, auth_headers, monkeypatch, db):
    """Invoices come through as nested JSON; flatten + coerce + persist."""
    payload = {"QueryResponse": {"Invoice": [
        {
            "Id": "INV-QBO-1",
            "DocNumber": "INV-QBO-1",
            "TxnDate": "2026-04-01",
            "DueDate": "2026-05-01",
            "TotalAmt": 4321.00,
            "CustomerRef": {"value": "1", "name": "Acme QBO"},
        },
    ]}}

    def handler(method, url, params, data, headers):
        return _resp(payload)

    _mock_httpx(monkeypatch, handler)
    r = client.post(
        "/api/v1/importers/jobs/api",
        headers=auth_headers,
        json={
            "source": "quickbooks",
            "target_entity": "invoice",
            "source_credentials": {"realm_id": REALM, "access_token": "tok"},
        },
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    sm = client.post(
        f"/api/v1/importers/jobs/{job_id}/suggest-mapping", headers=auth_headers,
    ).json()["mapping"]
    client.patch(
        f"/api/v1/importers/jobs/{job_id}/mapping",
        headers=auth_headers,
        json={"column_mapping": sm},
    )
    commit = client.post(f"/api/v1/importers/jobs/{job_id}/commit", headers=auth_headers)
    assert commit.status_code == 200, commit.text
    db.expire_all()
    inv = db.scalar(select(Invoice).where(Invoice.invoice_number == "INV-QBO-1"))
    assert inv is not None
    assert float(inv.total) == 4321.0


def test_qbo_cross_tenant_isolation(
    client, make_tenant, monkeypatch, session_factory,
):
    tenant_a, _, token_a = make_tenant("qbo-a")
    tenant_b, _, token_b = make_tenant("qbo-b")

    payload = {"QueryResponse": {"Customer": [
        {"Id": "iso", "DisplayName": "QBO Iso Cust"},
    ]}}

    def handler(method, url, params, data, headers):
        return _resp(payload)

    _mock_httpx(monkeypatch, handler)

    headers_a = {"Authorization": f"Bearer {token_a}"}
    r = client.post(
        "/api/v1/importers/jobs/api",
        headers=headers_a,
        json={
            "source": "quickbooks",
            "target_entity": "customer",
            "source_credentials": {"realm_id": REALM, "access_token": "tok"},
        },
    )
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
        rows = list(s.scalars(select(Customer).where(Customer.name == "QBO Iso Cust")))
        assert rows == []
    with session_factory() as s, tenant_scope(tenant_a.id):
        rows = list(s.scalars(select(Customer).where(Customer.name == "QBO Iso Cust")))
        assert len(rows) == 1
