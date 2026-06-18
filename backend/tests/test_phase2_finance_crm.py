"""Phase 2 — Finance + CRM hardening + the deal→invoice integration.

Covers:
  * Input validation rejections (bad currency, email, negative money,
    invalid stage/status, date order) → 422, friendly message.
  * Good input still accepted.
  * The CRM→Finance bridge: a won deal generates a draft invoice,
    idempotently, find-or-creating the customer.
  * Cascade integrity: deleting an invoice removes its lines.
"""
from __future__ import annotations

import uuid

import pytest


def _auth(client):
    r = client.post("/api/v1/auth/login",
                    json={"email": "admin@local", "password": "ChangeMe123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def hdr(client):
    return _auth(client)


# ---------------------------------------------------------------------------
# Validation — bad input must be rejected with 422
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body,field", [
    ({"name": "X", "currency": "XYZ"}, "currency"),
    ({"name": "X", "email": "not-an-email"}, "email"),
    ({"name": "   "}, "name"),
    ({"name": "X", "phone": "abc!!!"}, "phone"),
])
def test_customer_bad_input_rejected(client, hdr, body, field):
    r = client.post("/api/v1/finance/customers", json=body, headers=hdr)
    assert r.status_code == 422, f"{field}: expected 422, got {r.status_code} {r.text}"


def test_customer_good_input_accepted(client, hdr):
    sfx = uuid.uuid4().hex[:8]
    r = client.post("/api/v1/finance/customers",
                    json={"name": f"Valid {sfx}", "email": f"ok-{sfx}@valid.io", "currency": "EUR"},
                    headers=hdr)
    assert r.status_code in (200, 201), r.text
    assert r.json()["currency"] == "EUR"
    assert r.json()["email"] == f"ok-{sfx}@valid.io"


@pytest.mark.parametrize("body", [
    {"title": "T", "value": -5},
    {"title": "T", "probability": 150},
    {"title": "T", "stage": "banana"},
    {"title": "   "},
])
def test_deal_bad_input_rejected(client, hdr, body):
    r = client.post("/api/v1/crm/deals", json=body, headers=hdr)
    assert r.status_code == 422, f"expected 422, got {r.status_code} {r.text}"


def test_deal_good_input_accepted(client, hdr):
    r = client.post("/api/v1/crm/deals",
                    json={"title": "Valid deal", "value": 5000, "stage": "qualified", "probability": 40},
                    headers=hdr)
    assert r.status_code in (200, 201), r.text


def test_invoice_due_before_issue_rejected(client, hdr):
    r = client.post("/api/v1/finance/invoices", json={
        "issue_date": "2026-06-01", "due_date": "2026-05-01",
        "lines": [{"description": "x", "quantity": 1, "unit_price": 10}],
    }, headers=hdr)
    assert r.status_code == 422, r.text


def test_invoice_negative_line_price_rejected(client, hdr):
    r = client.post("/api/v1/finance/invoices", json={
        "issue_date": "2026-06-01", "due_date": "2026-07-01",
        "lines": [{"description": "x", "quantity": 1, "unit_price": -50}],
    }, headers=hdr)
    assert r.status_code == 422, r.text


def test_invoice_invalid_status_rejected(client, hdr):
    # Create a valid invoice first.
    inv = client.post("/api/v1/finance/invoices", json={
        "issue_date": "2026-06-01", "due_date": "2026-07-01",
        "lines": [{"description": "Consulting", "quantity": 2, "unit_price": 100}],
    }, headers=hdr)
    assert inv.status_code in (200, 201), inv.text
    iid = inv.json()["id"]
    bad = client.post(f"/api/v1/finance/invoices/{iid}/status",
                      json={"status": "banana"}, headers=hdr)
    assert bad.status_code == 422, bad.text


# ---------------------------------------------------------------------------
# CRM → Finance bridge — the keystone integration
# ---------------------------------------------------------------------------

def _make_won_deal(client, hdr, value=12500) -> str:
    # Create a contact then a won deal referencing it.
    sfx = uuid.uuid4().hex[:8]
    c = client.post("/api/v1/crm/contacts",
                    json={"name": f"Bridge Contact {sfx}", "company": f"BridgeCo {sfx}",
                          "email": f"bridge-{sfx}@co.io"}, headers=hdr)
    assert c.status_code in (200, 201), c.text
    cid = c.json()["id"]
    d = client.post("/api/v1/crm/deals",
                    json={"title": f"Bridge deal {sfx}", "contact_id": cid,
                          "value": value, "stage": "won", "probability": 100},
                    headers=hdr)
    assert d.status_code in (200, 201), d.text
    return d.json()["id"]


def test_deal_to_invoice_creates_draft(client, hdr):
    did = _make_won_deal(client, hdr, value=12500)
    before = len(client.get("/api/v1/finance/invoices", headers=hdr).json())
    r = client.post(f"/api/v1/crm/deals/{did}/invoice", headers=hdr)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] is True
    assert body["status"] == "draft"
    assert body["total"] == "12500.00"
    after = len(client.get("/api/v1/finance/invoices", headers=hdr).json())
    assert after == before + 1


def test_deal_to_invoice_is_idempotent(client, hdr):
    did = _make_won_deal(client, hdr, value=8000)
    first = client.post(f"/api/v1/crm/deals/{did}/invoice", headers=hdr).json()
    before = len(client.get("/api/v1/finance/invoices", headers=hdr).json())
    second = client.post(f"/api/v1/crm/deals/{did}/invoice", headers=hdr).json()
    after = len(client.get("/api/v1/finance/invoices", headers=hdr).json())
    assert first["created"] is True
    assert second["created"] is False
    assert second["invoice_number"] == first["invoice_number"]
    assert after == before  # no duplicate


def test_deal_to_invoice_finds_or_creates_customer(client, hdr):
    did = _make_won_deal(client, hdr, value=4200)
    r = client.post(f"/api/v1/crm/deals/{did}/invoice", headers=hdr).json()
    # The generated invoice must reference a real customer.
    inv = client.get("/api/v1/finance/invoices", headers=hdr).json()
    match = [i for i in inv if i["invoice_number"] == r["invoice_number"]]
    assert match and match[0]["customer_id"]


def test_zero_value_deal_not_invoiceable(client, hdr):
    sfx = uuid.uuid4().hex[:8]
    d = client.post("/api/v1/crm/deals",
                    json={"title": f"Zero deal {sfx}", "value": 0, "stage": "won"},
                    headers=hdr)
    did = d.json()["id"]
    r = client.post(f"/api/v1/crm/deals/{did}/invoice", headers=hdr)
    assert r.status_code == 422
    assert r.json()["code"] == "deal_not_invoiceable"


# ---------------------------------------------------------------------------
# Cascade integrity
# ---------------------------------------------------------------------------

def test_invoice_delete_cascades_lines(client, hdr, session_factory):
    from app.models.finance import InvoiceLine
    from sqlalchemy import select, func
    inv = client.post("/api/v1/finance/invoices", json={
        "issue_date": "2026-06-01", "due_date": "2026-07-01",
        "lines": [
            {"description": "A", "quantity": 1, "unit_price": 100},
            {"description": "B", "quantity": 2, "unit_price": 50},
        ],
    }, headers=hdr)
    iid = inv.json()["id"]
    with session_factory() as db:
        n = db.scalar(select(func.count(InvoiceLine.id)).where(InvoiceLine.invoice_id == iid))
        assert n == 2
    de = client.delete(f"/api/v1/finance/invoices/{iid}", headers=hdr)
    assert de.status_code in (200, 204), de.text
    with session_factory() as db:
        n = db.scalar(select(func.count(InvoiceLine.id)).where(InvoiceLine.invoice_id == iid))
        assert n == 0, "invoice lines should be cascade-deleted"
