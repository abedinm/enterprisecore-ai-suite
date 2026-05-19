"""Tests for the cursor pagination helper + retrofitted endpoints.

Covers:
  - Page envelope shape (items / total / page / page_size / total_pages)
  - 1-based paging math (page=2 skips page_size rows)
  - Hard ceiling at 200 page_size
  - Empty results return total_pages=0 (not a "page 1 of 1" lie)
  - users/page, notifications/page, finance/customers/page, finance/invoices/page
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from math import ceil

from sqlalchemy import select

from app.models.finance import Customer, Invoice
from app.models.user import Notification, User


def test_page_envelope_shape(client, auth_headers):
    r = client.get("/api/v1/users/page", headers=auth_headers, params={"page": 1, "page_size": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {"items", "total", "page", "page_size", "total_pages"}
    assert body["page"] == 1
    assert body["page_size"] == 5


def test_page_size_capped_at_200(client, auth_headers):
    r = client.get("/api/v1/users/page", headers=auth_headers, params={"page": 1, "page_size": 500})
    # Pydantic Query(le=200) returns 422
    assert r.status_code == 422


def test_page_zero_rejected(client, auth_headers):
    r = client.get("/api/v1/users/page", headers=auth_headers, params={"page": 0, "page_size": 10})
    assert r.status_code == 422


def test_paging_math_works(client, auth_headers, session_factory):
    # Plant 12 customers, all named so we can find them
    with session_factory() as db:
        # Clear any existing for a deterministic test
        for c in db.scalars(select(Customer).where(Customer.name.like("PG_%"))).all():
            db.delete(c)
        for i in range(12):
            db.add(Customer(name=f"PG_{i:02d}", email=f"pg{i}@x.test", currency="USD"))
        db.commit()

    page1 = client.get(
        "/api/v1/finance/customers/page",
        headers=auth_headers,
        params={"page": 1, "page_size": 5, "q": "PG_"},
    ).json()
    page2 = client.get(
        "/api/v1/finance/customers/page",
        headers=auth_headers,
        params={"page": 2, "page_size": 5, "q": "PG_"},
    ).json()
    page3 = client.get(
        "/api/v1/finance/customers/page",
        headers=auth_headers,
        params={"page": 3, "page_size": 5, "q": "PG_"},
    ).json()

    assert page1["total"] == 12
    assert page1["total_pages"] == ceil(12 / 5)
    assert len(page1["items"]) == 5
    assert len(page2["items"]) == 5
    assert len(page3["items"]) == 2  # last page

    # No overlap between pages
    ids = {x["id"] for x in page1["items"]} | {x["id"] for x in page2["items"]} | {x["id"] for x in page3["items"]}
    assert len(ids) == 12


def test_paging_empty_returns_zero_pages(client, auth_headers, session_factory):
    # filter that matches nothing
    r = client.get(
        "/api/v1/finance/customers/page",
        headers=auth_headers,
        params={"page": 1, "page_size": 10, "q": "definitely-does-not-exist-zzz"},
    )
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["total_pages"] == 0


def test_notifications_page(client, auth_headers, session_factory):
    admin = None
    with session_factory() as s:
        admin = s.scalar(select(User).where(User.email == "admin@local"))
        for i in range(8):
            s.add(Notification(user_id=admin.id, title=f"NP {i}", body="x", level="info"))
        s.commit()

    r = client.get(
        "/api/v1/notifications/page",
        headers=auth_headers,
        params={"page": 1, "page_size": 3},
    )
    body = r.json()
    assert body["page_size"] == 3
    assert len(body["items"]) == 3
    assert body["total"] >= 8


def test_invoices_page_has_nested_lines(client, auth_headers, session_factory):
    # Need at least one invoice with lines
    cust = client.post(
        "/api/v1/finance/customers",
        headers=auth_headers,
        json={"name": "PG Invoice Customer", "email": "pg@inv.test", "currency": "USD"},
    ).json()
    inv_payload = {
        "customer_id": cust["id"],
        "issue_date": str(date.today()),
        "due_date": str(date.today()),
        "currency": "USD",
        "notes": "pagination test",
        "discount_total": "0",
        "lines": [
            {"description": "Service", "quantity": "1", "unit_price": "100", "tax_rate": "0", "line_total": "100"},
        ],
    }
    client.post("/api/v1/finance/invoices", headers=auth_headers, json=inv_payload)

    r = client.get(
        "/api/v1/finance/invoices/page",
        headers=auth_headers,
        params={"page": 1, "page_size": 5},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body and "total" in body
    if body["items"]:
        first = body["items"][0]
        assert "lines" in first
        assert isinstance(first["lines"], list)
