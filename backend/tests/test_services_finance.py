"""Unit tests for the pure functions in services/finance.py — no DB, no HTTP."""
from __future__ import annotations

from decimal import Decimal

from app.services import finance as fin


def test_compute_line_total_zero_tax():
    sub, tax = fin.compute_line_total(10, 9.99, 0)
    assert sub == Decimal("99.90")
    assert tax == Decimal("0.00")


def test_compute_line_total_with_tax():
    sub, tax = fin.compute_line_total(2, 100, Decimal("0.20"))
    assert sub == Decimal("200.00")
    assert tax == Decimal("40.00")


def test_compute_line_total_rounds_half_up():
    # 0.115 → 0.12 with ROUND_HALF_UP
    sub, _ = fin.compute_line_total(1, Decimal("0.115"), 0)
    assert sub == Decimal("0.12")


def test_estimate_payroll_basic():
    out = fin.estimate_payroll(Decimal("5000"), tax_rate=Decimal("0.22"),
                               deductions=Decimal("200"), bonuses=Decimal("500"))
    assert out["gross"] == Decimal("5500.00")
    assert out["tax"] == Decimal("1210.00")
    assert out["deductions"] == Decimal("200.00")
    assert out["net"] == Decimal("4090.00")


def test_estimate_tax_zero_income_zero_tax():
    out = fin.estimate_tax(Decimal("0"))
    assert out["estimated_tax"] == Decimal("0.00")
    assert out["effective_rate"] == Decimal("0")


def test_estimate_tax_low_income_first_bracket_only():
    # 8k income, US default brackets, no deductions
    # 8000 falls entirely into the first bracket (0..11000 @ 10%) → 800 tax
    out = fin.estimate_tax(Decimal("8000"))
    assert out["taxable_income"] == Decimal("8000.00")
    assert out["estimated_tax"] == Decimal("800.00")


def test_estimate_tax_progressive_across_brackets():
    # 50k income, no deductions, US default brackets
    # 0..11000 @ 10% = 1100
    # 11000..44725 @ 12% = 4047
    # 44725..50000 @ 22% = 1160.50
    # total ≈ 6307.50
    out = fin.estimate_tax(Decimal("50000"))
    tax = out["estimated_tax"]
    assert Decimal("6300") < tax < Decimal("6320")
    assert Decimal("0.12") < out["effective_rate"] < Decimal("0.13")
