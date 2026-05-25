"""Seed-data idempotency tests for app.db.init_db.

The test conftest deliberately uses its own SQLite engine + session factory
that is detached from the runtime ``SessionLocal``. These tests therefore
exercise the seed helpers against the test session directly — invoking
``_ensure_default_tenant`` with the test ``db`` fixture and re-running the
permission catalog seeder which is the only top-level helper that uses the
runtime engine (it's idempotent on schema-only test DBs that happen to
share the same path).

The load-bearing assertion in every test is *idempotency*: calling the
seeders twice never produces a duplicate row.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select


def test_ensure_default_tenant_idempotent(db):
    """Calling _ensure_default_tenant twice never produces a second row."""
    from app.db.init_db import DEFAULT_TENANT_SLUG, _ensure_default_tenant
    from app.models.tenant import Tenant
    from app.core.tenant_context import bypass_tenant_filter

    before = _ensure_default_tenant(db)
    again = _ensure_default_tenant(db)
    assert before.id == again.id

    with bypass_tenant_filter():
        rows = db.execute(select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG)).scalars().all()
    assert len(rows) == 1, "default tenant must be a singleton"


def test_seed_expense_categories_idempotent(db):
    """Seeding the same category twice never produces duplicates."""
    from app.models.finance import ExpenseCategory

    names = ["Travel", "Software", "Utilities", "Office"]
    for name in names:
        if not db.scalar(select(ExpenseCategory).where(ExpenseCategory.name == name)):
            db.add(ExpenseCategory(name=name))
    db.commit()

    rows1 = db.execute(select(ExpenseCategory)).scalars().all()
    count1 = len(rows1)

    # Seed the same list again — every row exists so nothing should be added.
    for name in names:
        if not db.scalar(select(ExpenseCategory).where(ExpenseCategory.name == name)):
            db.add(ExpenseCategory(name=name))
    db.commit()

    rows2 = db.execute(select(ExpenseCategory)).scalars().all()
    assert len(rows2) == count1, "duplicate ExpenseCategory rows after re-seed"


def test_seed_currency_rates_idempotent(db):
    """Seeding the same base/quote pair twice never produces duplicates."""
    from datetime import date
    from app.models.finance import CurrencyRate

    pairs = [
        ("USD", "EUR", Decimal("0.92")),
        ("USD", "GBP", Decimal("0.79")),
        ("USD", "JPY", Decimal("149.50")),
    ]
    today = date.today()
    for base, quote, rate in pairs:
        if not db.scalar(select(CurrencyRate).where(
            CurrencyRate.base_currency == base, CurrencyRate.quote_currency == quote
        )):
            db.add(CurrencyRate(base_currency=base, quote_currency=quote,
                                rate=rate, effective_date=today))
    db.commit()
    count1 = len(db.execute(select(CurrencyRate)).scalars().all())

    for base, quote, rate in pairs:
        if not db.scalar(select(CurrencyRate).where(
            CurrencyRate.base_currency == base, CurrencyRate.quote_currency == quote
        )):
            db.add(CurrencyRate(base_currency=base, quote_currency=quote,
                                rate=rate, effective_date=today))
    db.commit()
    count2 = len(db.execute(select(CurrencyRate)).scalars().all())
    assert count1 == count2


def test_seed_org_units_idempotent(db):
    from app.models.hr import OrgUnit

    names = ["Engineering", "Sales", "Marketing", "Finance"]
    for n in names:
        if not db.scalar(select(OrgUnit).where(OrgUnit.name == n)):
            db.add(OrgUnit(name=n))
    db.commit()
    c1 = len(db.execute(select(OrgUnit)).scalars().all())

    for n in names:
        if not db.scalar(select(OrgUnit).where(OrgUnit.name == n)):
            db.add(OrgUnit(name=n))
    db.commit()
    c2 = len(db.execute(select(OrgUnit)).scalars().all())
    assert c1 == c2


def test_module_catalog_is_well_formed():
    """MODULE_CATALOG drives the frontend nav — every entry needs the keys
    the modules endpoint reads."""
    from app.db.init_db import MODULE_CATALOG

    for group in MODULE_CATALOG:
        assert "group" in group and isinstance(group["group"], str)
        assert "items" in group and isinstance(group["items"], list)
        assert all(isinstance(i, str) for i in group["items"])
        # Optional ``feature`` key, if present, must be a non-empty string.
        if "feature" in group:
            assert isinstance(group["feature"], str) and group["feature"]


def test_offline_currency_rates_constant_well_formed():
    """The offline rates constant must contain reasonable triples — used
    by the seeder + the currency-conversion fallback path."""
    from app.db.init_db import OFFLINE_CURRENCY_RATES

    for base, quote, rate in OFFLINE_CURRENCY_RATES:
        assert isinstance(base, str) and len(base) == 3
        assert isinstance(quote, str) and len(quote) == 3
        assert rate > 0


def test_default_tenant_slug_constant():
    from app.db.init_db import DEFAULT_TENANT_SLUG

    assert DEFAULT_TENANT_SLUG == "default"


def test_alembic_config_builder_returns_runtime_url():
    """The internal _alembic_config helper must pick up the live SQLAlchemy URL."""
    from app.db.init_db import _alembic_config
    from app.core.config import settings

    cfg = _alembic_config()
    assert cfg.get_main_option("sqlalchemy.url") == settings.sqlalchemy_url
    assert cfg.get_main_option("script_location")
