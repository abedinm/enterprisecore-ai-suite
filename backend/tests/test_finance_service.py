"""Service-level finance tests — targets the math/forecasting/multi-currency
helpers that were only ~47% covered by the HTTP-level finance suite.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.finance import (
    CurrencyRate,
    Customer,
    Expense,
    ExpenseCategory,
    Invoice,
    InvoiceLine,
)
from app.services import finance as fin


@pytest.fixture()
def fin_seed(session_factory):
    """Plant a deterministic set of customers/invoices/expenses for report math."""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    with session_factory() as db:
        cust = Customer(name=f"FS_Acme_{suffix}", email=f"a-{suffix}@fs.test", currency="USD")
        db.add(cust)
        db.flush()
        cat = ExpenseCategory(name=f"FS_Travel_{suffix}")
        db.add(cat)
        db.flush()

        today = date.today()
        # Two paid invoices and one sent — unique numbers per test run
        for n, total, status in ((f"FS-{suffix}-001", "1200", "paid"),
                                 (f"FS-{suffix}-002", "800", "paid"),
                                 (f"FS-{suffix}-003", "500", "sent")):
            inv = Invoice(
                invoice_number=n, customer_id=cust.id,
                issue_date=today - timedelta(days=10),
                due_date=today + timedelta(days=20),
                currency="USD", subtotal=Decimal(total),
                tax_total=Decimal("0"), discount_total=Decimal("0"),
                total=Decimal(total), status=status,
            )
            db.add(inv)
            db.flush()
            db.add(InvoiceLine(
                invoice_id=inv.id, description="Service",
                quantity=Decimal("1"), unit_price=Decimal(total),
                tax_rate=Decimal("0"), line_total=Decimal(total),
            ))

        # Some expenses, different currencies
        db.add(Expense(category_id=cat.id, date=today - timedelta(days=5),
                       amount=Decimal("200"), currency="USD", description="cab"))
        db.add(Expense(category_id=cat.id, date=today - timedelta(days=2),
                       amount=Decimal("400"), currency="USD", description="hotel"))
        db.add(Expense(category_id=cat.id, date=today - timedelta(days=1),
                       amount=Decimal("100"), currency="EUR", description="EU"))
        db.commit()
        yield cust.id


# ---- currency conversion -------------------------------------------------

def test_find_rate_identity(db):
    assert fin.find_rate(db, "USD", "USD") == Decimal("1")
    assert fin.find_rate(db, "eur", "eur") == Decimal("1")  # case insensitive


def test_find_rate_inverse_lookup(session_factory):
    with session_factory() as db:
        # Seed only one direction: USD -> XYZ at 2.5
        db.add(CurrencyRate(base_currency="USD", quote_currency="XYZ",
                            rate=Decimal("2.5"), effective_date=date.today()))
        db.commit()

        # Reverse direction should yield 1/2.5 = 0.4
        rate = fin.find_rate(db, "XYZ", "USD")
        assert rate == Decimal("0.4").quantize(Decimal("0.00000001"))


def test_find_rate_triangulates_via_usd(session_factory):
    with session_factory() as db:
        db.add(CurrencyRate(base_currency="USD", quote_currency="AAA",
                            rate=Decimal("2.0"), effective_date=date.today()))
        db.add(CurrencyRate(base_currency="USD", quote_currency="BBB",
                            rate=Decimal("4.0"), effective_date=date.today()))
        db.commit()
        # AAA -> BBB via USD: (1/2) * 4 = 2
        rate = fin.find_rate(db, "AAA", "BBB")
        assert rate == Decimal("2").quantize(Decimal("0.00000001"))


def test_find_rate_unknown_raises(session_factory):
    with session_factory() as db:
        with pytest.raises(ValueError, match="No exchange rate"):
            fin.find_rate(db, "QQQ", "ZZZ")


def test_convert_rounds_to_cents(session_factory):
    with session_factory() as db:
        db.add(CurrencyRate(base_currency="USD", quote_currency="EUR",
                            rate=Decimal("0.9123"), effective_date=date.today()))
        db.commit()
        out = fin.convert(db, Decimal("100"), "USD", "EUR")
        # 100 * 0.9123 = 91.23
        assert out["converted"] == Decimal("91.23")
        assert out["rate"] == Decimal("0.9123")
        assert out["from_currency"] == "USD"
        assert out["to_currency"] == "EUR"


# ---- multi-currency summary ---------------------------------------------

def test_multi_currency_summary_buckets(session_factory, fin_seed):
    with session_factory() as db:
        summary = fin.multi_currency_summary(db)
    assert "currencies" in summary
    usd = next((c for c in summary["currencies"] if c["currency"] == "USD"), None)
    assert usd is not None
    # 1200 + 800 paid; 500 sent (outstanding)
    assert usd["paid"] >= Decimal("2000")
    assert usd["outstanding"] >= Decimal("500")
    assert usd["expenses"] >= Decimal("600")  # 200 + 400 USD expenses


# ---- profit and loss ----------------------------------------------------

def test_pnl_basic(session_factory, fin_seed):
    with session_factory() as db:
        result = fin.profit_and_loss(db, date.today() - timedelta(days=30), date.today())
    # Three FS_ invoices totalling 2500 (all not-void within window)
    assert result["revenue"] >= Decimal("2500")
    # Expenses sum across all currencies — 200 + 400 USD + 100 EUR = 700 raw decimal
    assert result["operating_expenses"] >= Decimal("700")
    assert "net_income" in result
    assert result["net_income"] == result["gross_profit"] - result["operating_expenses"]
    assert result["cogs"] == Decimal("0.00")
    # by_category should include the fixture's seeded category
    assert any(name.startswith("FS_Travel_") for name in result["by_category"])


def test_pnl_excludes_void_invoices(session_factory):
    with session_factory() as db:
        cust = Customer(name="FS_Void", email="v@fs.test", currency="USD")
        db.add(cust)
        db.flush()
        today = date.today()
        db.add(Invoice(
            invoice_number="VOID-001", customer_id=cust.id,
            issue_date=today, due_date=today,
            currency="USD", total=Decimal("9999"), status="void",
        ))
        db.commit()

        result = fin.profit_and_loss(db, today - timedelta(days=1), today + timedelta(days=1))
    # Void invoice MUST NOT inflate revenue
    assert result["revenue"] < Decimal("9999")


# ---- payroll estimate ---------------------------------------------------

def test_payroll_estimate_basic():
    result = fin.estimate_payroll(
        Decimal("5000"),
        pay_frequency="monthly",
        tax_rate=Decimal("0.20"),
        deductions=Decimal("100"),
        bonuses=Decimal("200"),
    )
    # Gross = salary + bonuses = 5200. Tax = 1040. Net = gross - tax - deductions = 4060
    assert result["gross"] == Decimal("5200.00")
    assert result["tax"] == Decimal("1040.00")
    assert result["deductions"] == Decimal("100.00")
    assert result["bonuses"] == Decimal("200.00")
    assert result["net"] == Decimal("4060.00")
    assert result["frequency"] == "monthly"


def test_payroll_estimate_zero_tax():
    result = fin.estimate_payroll(
        Decimal("3000"),
        pay_frequency="monthly",
        tax_rate=Decimal("0"),
        deductions=Decimal("0"),
        bonuses=Decimal("0"),
    )
    assert result["tax"] == Decimal("0.00")
    assert result["net"] == Decimal("3000.00")


# ---- tax estimate (progressive brackets) --------------------------------

def test_estimate_tax_zero_income():
    result = fin.estimate_tax(Decimal("0"))
    assert result["estimated_tax"] == Decimal("0.00")
    assert result["effective_rate"] == Decimal("0")


def test_estimate_tax_custom_brackets():
    # Brackets are (threshold, rate). Final entry threshold=0 means "top marginal".
    brackets = [
        (Decimal("10000"), Decimal("0.10")),
        (Decimal("30000"), Decimal("0.20")),
        (Decimal("0"), Decimal("0.30")),
    ]
    # Income 25k → 10k*0.10 + 15k*0.20 = 1000 + 3000 = 4000
    result = fin.estimate_tax(Decimal("25000"), brackets=brackets)
    assert result["estimated_tax"] == Decimal("4000.00")
    assert result["taxable_income"] == Decimal("25000.00")
    assert len(result["breakdown"]) == 2


def test_estimate_tax_deductions_clipped_to_income():
    # Deductions can't push income below zero
    result = fin.estimate_tax(Decimal("1000"), deductions=Decimal("5000"))
    assert result["taxable_income"] == Decimal("0.00")
    assert result["estimated_tax"] == Decimal("0.00")
