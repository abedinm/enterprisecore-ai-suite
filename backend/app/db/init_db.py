"""Database bootstrap, migrations runner, and seed data."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from loguru import logger
from sqlalchemy import inspect, select

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import *  # noqa: F403
from app.models.finance import CurrencyRate, ExpenseCategory, TaxRate
from app.models.hr import OrgUnit
from app.models.user import Notification, Setting, User, UserRole

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def _alembic_config():
    """Build an Alembic Config that points at the runtime SQLAlchemy URL."""
    from alembic.config import Config
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.sqlalchemy_url)
    return cfg


def migrate_db() -> None:
    """Bring the schema up to head.

    * Fresh database → ``alembic upgrade head`` creates every table AND stamps
      the version row so subsequent ``alembic upgrade head`` calls only apply
      new migrations.
    * Existing database that was created with ``Base.metadata.create_all`` (no
      ``alembic_version`` table) → we stamp it at ``head`` first so alembic
      knows the current state, then proceed.
    * Existing database with an alembic version → straight upgrade.
    """
    from alembic import command

    cfg = _alembic_config()
    has_version_table = inspect(engine).has_table("alembic_version")
    users_table_exists = inspect(engine).has_table("users")
    if users_table_exists and not has_version_table:
        logger.info("DB has tables but no alembic_version — stamping at head")
        command.stamp(cfg, "head")
    command.upgrade(cfg, "head")
    logger.info("Migrations applied; DB is at head")

MODULE_CATALOG = [
    {"group": "Foundation", "items": ["Authentication", "Roles", "Settings", "Theme", "Offline sync", "Notifications", "Search", "Dashboard"]},
    {"group": "Finance", "items": ["Invoices", "Expenses", "Payroll", "Tax", "Budgets", "Profit & Loss", "Balance Sheet", "Cash Flow", "Forecasting", "Currencies", "Recurring Payments", "Vendor Payments", "Audit Trail", "Multi-Currency", "Reports Dashboard"]},
    {"group": "HR", "items": ["Employees", "Attendance", "Leave", "Reviews", "Recruitment", "Onboarding", "Org Chart", "Payslips", "Training", "Self Service", "Discipline", "Analytics"]},
    {"group": "CRM", "items": ["Leads", "Pipeline", "Customers", "Follow-ups", "Forecasting", "Communication Log", "Contracts", "Proposals", "Analytics", "Segments", "Campaigns", "Quotes"]},
    {"group": "Projects", "items": ["Kanban", "Gantt", "Time", "Tasks", "Resources", "Milestones", "Workload", "Sprints", "Meetings", "Analytics"]},
    {"group": "Inventory", "items": ["Stock", "Purchase Orders", "Suppliers", "Warehouses", "Low Stock", "Barcodes", "Shipments", "Catalog", "Returns", "Analytics"]},
    {"group": "Documents", "items": ["Editor", "PDF", "E-signature", "Templates", "Organizer", "Versions", "Bulk Rename", "Sharing"]},
    {"group": "Communication", "items": ["Messages", "Announcements", "Calendar", "Meetings", "Notes", "Polls", "Feedback", "Wiki"]},
    {"group": "Security", "items": ["Access Control", "Audit Logs", "Password Vault", "GDPR", "Backups", "Encryption", "Login Monitor", "Reports"]},
    {"group": "AI Coding", "items": ["Editor", "Explorer", "Terminal", "AI Chat", "Generation", "Explanation", "Bug Fixing", "Review", "Multi-file Editing", "Git", "Snippets", "API Tester", "DB Builder", "Regex Builder"]},
    {"group": "AI Brain", "items": ["Writer", "Meeting Summary", "Financial Narrator", "HR Insights", "Sales Forecasting", "Invoice Analyzer", "Contract Risk", "Smart Search", "Chatbot Builder", "Sentiment", "Ollama", "Usage"]},
]

# Offline reference rates against USD (snapshot Q1 2026). All can be edited in-app.
OFFLINE_CURRENCY_RATES: list[tuple[str, str, Decimal]] = [
    ("USD", "USD", Decimal("1")),
    ("USD", "EUR", Decimal("0.92")),
    ("USD", "GBP", Decimal("0.79")),
    ("USD", "JPY", Decimal("149.50")),
    ("USD", "CAD", Decimal("1.36")),
    ("USD", "AUD", Decimal("1.52")),
    ("USD", "CHF", Decimal("0.88")),
    ("USD", "CNY", Decimal("7.20")),
    ("USD", "INR", Decimal("83.20")),
    ("USD", "MXN", Decimal("17.10")),
    ("USD", "BRL", Decimal("4.95")),
    ("USD", "ZAR", Decimal("18.70")),
    ("USD", "SEK", Decimal("10.45")),
    ("USD", "NOK", Decimal("10.60")),
    ("USD", "DKK", Decimal("6.85")),
    ("USD", "SGD", Decimal("1.34")),
    ("USD", "HKD", Decimal("7.80")),
    ("USD", "NZD", Decimal("1.64")),
    ("USD", "KRW", Decimal("1330.00")),
    ("USD", "TRY", Decimal("32.50")),
    ("USD", "AED", Decimal("3.67")),
    ("USD", "SAR", Decimal("3.75")),
    ("USD", "PLN", Decimal("4.00")),
]


def init_db() -> None:
    """Run migrations to head, then seed first-run data (admin, settings, etc.)."""
    migrate_db()
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == "admin@local"))
        if not admin:
            admin = User(
                email="admin@local",
                full_name="EnterpriseCore Admin",
                password_hash=hash_password("ChangeMe123!"),
                role=UserRole.admin,
            )
            db.add(admin)
            db.flush()
            db.add(
                Notification(
                    user_id=admin.id,
                    title="Welcome to EnterpriseCore AI Suite",
                    body="Phase 1 foundation is ready. Change the default admin password before production use.",
                    level="success",
                )
            )

        defaults = {
            "company.name": "Your Company",
            "company.currency": settings.default_currency,
            "app.locale": settings.default_locale,
            "app.timezone": settings.default_timezone,
            "ai.provider": settings.ai_default_provider,
            "offline.enabled": "true",
            "module.catalog": json.dumps(MODULE_CATALOG),
        }
        for key, value in defaults.items():
            if not db.scalar(select(Setting).where(Setting.scope == "global", Setting.key == key)):
                db.add(Setting(scope="global", key=key, value=value))

        for name in ["Travel", "Software", "Utilities", "Office", "Payroll",
                     "Marketing", "Rent", "Insurance", "Professional Services",
                     "Equipment", "Meals", "Training"]:
            if not db.scalar(select(ExpenseCategory).where(ExpenseCategory.name == name)):
                db.add(ExpenseCategory(name=name))

        for jurisdiction, name, rate in [
            ("Default", "Standard VAT/GST", Decimal("0")),
            ("US", "Sales Tax", Decimal("0.08")),
            ("UK", "VAT", Decimal("0.20")),
            ("EU", "VAT (standard)", Decimal("0.21")),
            ("CA", "GST/HST", Decimal("0.13")),
            ("AU", "GST", Decimal("0.10")),
        ]:
            if not db.scalar(select(TaxRate).where(
                TaxRate.jurisdiction == jurisdiction, TaxRate.name == name
            )):
                db.add(TaxRate(jurisdiction=jurisdiction, name=name, rate=rate))

        # Seed default org units (flat structure to start)
        for org_name in ["Engineering", "Sales", "Marketing", "Finance",
                         "HR", "Operations", "Support"]:
            if not db.scalar(select(OrgUnit).where(OrgUnit.name == org_name)):
                db.add(OrgUnit(name=org_name))

        today = date.today()
        for base, quote, rate in OFFLINE_CURRENCY_RATES:
            exists = db.scalar(
                select(CurrencyRate).where(
                    CurrencyRate.base_currency == base,
                    CurrencyRate.quote_currency == quote,
                )
            )
            if not exists:
                db.add(CurrencyRate(base_currency=base, quote_currency=quote,
                                    rate=rate, effective_date=today))

        db.commit()
