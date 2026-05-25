"""Multi-entity consolidation tests (Phase 10).

Covers:
* Subsidiary entity CRUD
* Intercompany transaction creation + elimination on consolidation
* Balance-sheet consolidation translating GBP + SGD entities to USD
* P&L consolidation with intercompany revenue + expense wash-out
* FX revaluation generating non-zero adjustment when rates move
* Cross-tenant entity isolation
* Default tenant has exactly one main entity

Data-creating tests use a *fresh* per-test tenant via the ``make_tenant``
fixture so the default tenant's running totals stay clean for any
finance-service test that asserts revenue/expense thresholds.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.tenant_context import tenant_scope
from app.models.finance import CurrencyRate, Expense, Invoice
from app.models.finance_consolidation import (
    IntercompanyTransaction,
    SubsidiaryEntity,
)
from app.services import consolidation as consol
from app.services.consolidation import get_or_create_main_entity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _seed_rate(db, base, quote, rate, as_of=None):
    db.add(CurrencyRate(
        base_currency=base, quote_currency=quote,
        rate=Decimal(str(rate)),
        effective_date=as_of or date.today(),
    ))
    db.flush()


def _ensure_main(db, tenant_currency="USD"):
    return get_or_create_main_entity(db, tenant_currency=tenant_currency)


# ---------------------------------------------------------------------------
# 1. Default tenant gets a main entity on demand
# ---------------------------------------------------------------------------
def test_default_tenant_main_entity(db):
    main = _ensure_main(db, "USD")
    db.commit()
    assert main.is_main is True
    assert main.code == "MAIN"


# ---------------------------------------------------------------------------
# 2. Entity CRUD via API (default tenant — no money rows added)
# ---------------------------------------------------------------------------
def test_entity_crud(client, auth_headers, db):
    _ensure_main(db, "USD")
    db.commit()

    r = client.post(
        "/api/v1/finance/entities", headers=auth_headers,
        json={
            "name": "UK Limited", "code": "UK-LTD-CRUD", "country": "GB",
            "functional_currency": "GBP", "reporting_currency": "USD",
        },
    )
    assert r.status_code == 200, r.text
    uk = r.json()
    assert uk["functional_currency"] == "GBP"
    assert uk["is_main"] is False

    listing = client.get("/api/v1/finance/entities", headers=auth_headers)
    assert listing.status_code == 200
    codes = {e["code"] for e in listing.json()}
    assert "MAIN" in codes and "UK-LTD-CRUD" in codes

    patch = client.patch(
        f"/api/v1/finance/entities/{uk['id']}", headers=auth_headers,
        json={"is_active": False},
    )
    assert patch.status_code == 200
    assert patch.json()["is_active"] is False


# ---------------------------------------------------------------------------
# 3. Balance-sheet consolidation: GBP + SGD → USD (isolated tenant)
# ---------------------------------------------------------------------------
def test_balance_sheet_consolidation_translates_to_usd(session_factory, make_tenant):
    tenant, _, _ = make_tenant("consol-bs")
    today = date.today()

    with session_factory() as db, tenant_scope(tenant.id):
        uk = SubsidiaryEntity(
            name="UK Ltd", code="UK-LTD", country="GB",
            functional_currency="GBP", reporting_currency="USD",
            is_main=False, is_active=True,
        )
        sg = SubsidiaryEntity(
            name="SG Pte", code="SG-PTE", country="SG",
            functional_currency="SGD", reporting_currency="USD",
            is_main=False, is_active=True,
        )
        db.add(uk); db.add(sg)
        db.flush()

        _seed_rate(db, "GBP", "USD", "1.25", today)
        _seed_rate(db, "SGD", "USD", "0.74", today)

        db.add(Invoice(
            invoice_number="UK-001", customer_id=None, entity_id=uk.id,
            issue_date=today, due_date=today, status="sent",
            currency="GBP", subtotal=Decimal("1000"), tax_total=Decimal("0"),
            discount_total=Decimal("0"), total=Decimal("1000"),
        ))
        db.add(Invoice(
            invoice_number="SG-001", customer_id=None, entity_id=sg.id,
            issue_date=today, due_date=today, status="sent",
            currency="SGD", subtotal=Decimal("2000"), tax_total=Decimal("0"),
            discount_total=Decimal("0"), total=Decimal("2000"),
        ))
        db.commit()

        result = consol.consolidate_balance_sheet(
            db, as_of=today, target_currency="USD",
            entity_ids=[uk.id, sg.id],
        )

    assert result["target_currency"] == "USD"
    expected = Decimal("1250.00") + Decimal("1480.00")
    assert result["consolidated"]["total_assets"] == expected
    by_code = {e["code"]: e for e in result["entities"]}
    assert by_code["UK-LTD"]["translated"]["total_assets"] == Decimal("1250.00")
    assert by_code["SG-PTE"]["translated"]["total_assets"] == Decimal("1480.00")


# ---------------------------------------------------------------------------
# 4. Intercompany eliminations on consolidated P&L (isolated tenant)
# ---------------------------------------------------------------------------
def test_intercompany_elimination_pnl(session_factory, make_tenant):
    tenant, _, _ = make_tenant("consol-pnl")
    today = date.today()
    period_start = today - timedelta(days=30)

    with session_factory() as db, tenant_scope(tenant.id):
        a = SubsidiaryEntity(
            name="A Co", code="A-CO", country="US",
            functional_currency="USD", reporting_currency="USD", is_active=True,
        )
        b = SubsidiaryEntity(
            name="B Co", code="B-CO", country="US",
            functional_currency="USD", reporting_currency="USD", is_active=True,
        )
        db.add(a); db.add(b)
        db.flush()

        db.add(Invoice(
            invoice_number="A-EXT-1", entity_id=a.id, customer_id=None,
            issue_date=today, due_date=today, status="sent",
            currency="USD", subtotal=Decimal("5000"), total=Decimal("5000"),
        ))
        db.add(Invoice(
            invoice_number="B-EXT-1", entity_id=b.id, customer_id=None,
            issue_date=today, due_date=today, status="sent",
            currency="USD", subtotal=Decimal("3000"), total=Decimal("3000"),
        ))
        # Intercompany leg: A bills B 1000 — modelled in standalone books
        # too: A has +1000 invoice; B has +1000 expense.
        db.add(Invoice(
            invoice_number="A-IC-1", entity_id=a.id, customer_id=None,
            issue_date=today, due_date=today, status="sent",
            currency="USD", subtotal=Decimal("1000"), total=Decimal("1000"),
        ))
        db.add(Expense(
            entity_id=b.id, date=today, amount=Decimal("1000"),
            currency="USD", description="IC mgmt fee from A",
        ))
        db.add(IntercompanyTransaction(
            from_entity_id=a.id, to_entity_id=b.id,
            kind="management_fee", amount=Decimal("1000"), currency="USD",
            transaction_date=today, eliminates_on_consolidation=True,
        ))
        db.commit()

        result = consol.consolidate_pnl(
            db, period_start=period_start, period_end=today,
            target_currency="USD", entity_ids=[a.id, b.id],
        )

    assert result["consolidated"]["revenue"] == Decimal("8000.00")
    assert result["consolidated"]["expenses"] == Decimal("0.00")
    assert result["consolidated"]["net_income"] == Decimal("8000.00")
    assert len(result["eliminations"]) == 1


# ---------------------------------------------------------------------------
# 5. FX revaluation produces non-zero adjustment when rates move
# ---------------------------------------------------------------------------
def test_fx_revaluation_creates_adjustment(session_factory, make_tenant):
    tenant, _, _ = make_tenant("consol-fx")
    today = date.today()
    last_month = today - timedelta(days=30)

    with session_factory() as db, tenant_scope(tenant.id):
        uk = SubsidiaryEntity(
            name="UK Ltd FX", code="UK-LTD-FX", country="GB",
            functional_currency="GBP", reporting_currency="USD", is_active=True,
        )
        db.add(uk)
        db.flush()

        # Foreign-currency AR: EUR invoice on a GBP-functional entity.
        db.add(Invoice(
            invoice_number="UK-EURAR-1", entity_id=uk.id, customer_id=None,
            issue_date=today - timedelta(days=15), due_date=today, status="sent",
            currency="EUR", subtotal=Decimal("10000"), total=Decimal("10000"),
        ))
        _seed_rate(db, "EUR", "USD", "1.05", last_month)
        _seed_rate(db, "EUR", "USD", "1.10", today)
        db.commit()

        adjustments = consol.fx_revaluation(
            db, entity_id=uk.id, period_end=today,
        )
        db.commit()

        ar_adj = [a for a in adjustments if a.account_kind == "ar"]
        assert len(ar_adj) == 1
        adj = ar_adj[0]
        assert adj.original_currency == "EUR"
        assert adj.fx_gain_loss == Decimal("500.00")
        assert adj.original_amount == Decimal("10000.00")


# ---------------------------------------------------------------------------
# 6. Cross-tenant isolation — entities don't leak between tenants
# ---------------------------------------------------------------------------
def test_entity_cross_tenant_isolation(session_factory, make_tenant):
    a, _, _ = make_tenant("consol-a")
    b, _, _ = make_tenant("consol-b")

    with session_factory() as s, tenant_scope(a.id):
        s.add(SubsidiaryEntity(
            name="A Main", code="MAIN", country="US",
            functional_currency="USD", reporting_currency="USD",
            is_main=True, is_active=True,
        ))
        s.add(SubsidiaryEntity(
            name="A UK", code="A-UK", country="GB",
            functional_currency="GBP", reporting_currency="USD",
            is_active=True,
        ))
        s.commit()

    with session_factory() as s, tenant_scope(b.id):
        s.add(SubsidiaryEntity(
            name="B Main", code="MAIN", country="US",
            functional_currency="USD", reporting_currency="USD",
            is_main=True, is_active=True,
        ))
        s.commit()

    with session_factory() as s, tenant_scope(a.id):
        codes = sorted(e.code for e in s.scalars(select(SubsidiaryEntity)))
        assert codes == ["A-UK", "MAIN"]

    with session_factory() as s, tenant_scope(b.id):
        codes = sorted(e.code for e in s.scalars(select(SubsidiaryEntity)))
        assert codes == ["MAIN"]


# ---------------------------------------------------------------------------
# 7. Single main entity per tenant — API rejects a second
# ---------------------------------------------------------------------------
def test_only_one_main_entity_per_tenant(client, auth_headers, db):
    _ensure_main(db, "USD")
    db.commit()
    r = client.post(
        "/api/v1/finance/entities", headers=auth_headers,
        json={
            "name": "Second Main", "code": "MAIN-2", "country": "US",
            "functional_currency": "USD", "reporting_currency": "USD",
            "is_main": True,
        },
    )
    assert r.status_code in (400, 409), r.text


# ---------------------------------------------------------------------------
# 8. Intercompany transaction API end-to-end
# ---------------------------------------------------------------------------
def test_intercompany_api(client, auth_headers, db):
    _ensure_main(db, "USD")
    db.commit()

    e1 = client.post(
        "/api/v1/finance/entities", headers=auth_headers,
        json={"name": "Sub 1", "code": "SUB-1", "country": "US",
              "functional_currency": "USD", "reporting_currency": "USD"},
    ).json()
    e2 = client.post(
        "/api/v1/finance/entities", headers=auth_headers,
        json={"name": "Sub 2", "code": "SUB-2", "country": "US",
              "functional_currency": "USD", "reporting_currency": "USD"},
    ).json()

    r = client.post(
        "/api/v1/finance/intercompany", headers=auth_headers,
        json={
            "from_entity_id": e1["id"], "to_entity_id": e2["id"],
            "kind": "loan", "amount": "5000", "currency": "USD",
            "transaction_date": date.today().isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "loan"
    assert Decimal(str(body["amount"])) == Decimal("5000")

    bad = client.post(
        "/api/v1/finance/intercompany", headers=auth_headers,
        json={
            "from_entity_id": e1["id"], "to_entity_id": e1["id"],
            "kind": "loan", "amount": "100", "currency": "USD",
            "transaction_date": date.today().isoformat(),
        },
    )
    assert bad.status_code in (400, 422)


# ---------------------------------------------------------------------------
# 9. fx-revaluation endpoint persists adjustments
# ---------------------------------------------------------------------------
def test_fx_revaluation_endpoint(session_factory, make_tenant, client):
    """Drive the endpoint inside a fresh tenant so we don't pollute the
    default-tenant invoice totals."""
    from app.core.security import create_access_token
    from app.models.user import User

    tenant, user, token = make_tenant("consol-fx-api")
    headers = {"Authorization": f"Bearer {token}"}
    today = date.today()
    last_month = today - timedelta(days=30)

    with session_factory() as db, tenant_scope(tenant.id):
        uk = SubsidiaryEntity(
            name="UK Ltd 2", code="UK-LTD2", country="GB",
            functional_currency="GBP", reporting_currency="USD", is_active=True,
        )
        db.add(uk)
        db.flush()
        db.add(Invoice(
            invoice_number="UK-EURAR-2", entity_id=uk.id, customer_id=None,
            issue_date=today - timedelta(days=10), due_date=today, status="sent",
            currency="EUR", subtotal=Decimal("5000"), total=Decimal("5000"),
        ))
        _seed_rate(db, "EUR", "USD", "1.00", last_month)
        _seed_rate(db, "EUR", "USD", "1.20", today)
        db.commit()
        uk_id = uk.id

    r = client.post(
        "/api/v1/finance/fx-revaluation", headers=headers,
        json={"entity_id": uk_id, "period_end": today.isoformat()},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list) and len(body) >= 1
    ar = [a for a in body if a["account_kind"] == "ar"]
    assert len(ar) == 1
    assert Decimal(str(ar[0]["fx_gain_loss"])) == Decimal("1000.00")

    listing = client.get(
        f"/api/v1/finance/fx-revaluation?entity_id={uk_id}",
        headers=headers,
    )
    assert listing.status_code == 200
    assert len(listing.json()) >= 1
