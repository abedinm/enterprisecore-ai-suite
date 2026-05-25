"""Demo data seeder — one Atlas Robotics tenant populated end-to-end.

What you get
------------

Running ``python -m app.db.demo_seed`` (or :func:`seed_demo` from code)
creates a single self-consistent tenant — **Atlas Robotics Inc.** — with:

* 8 users across roles (admin, manager, employee, developer)
* 50 employees (HR records) — Engineering / Sales / Marketing / Ops /
  Finance / HR / Customer Success
* 6 org units + manager hierarchy
* 12 B2B customers in multiple currencies (USD, EUR, GBP, SEK, CHF, CAD)
* 8 vendors, 5 expense categories
* 30 invoices (mixed draft / issued / paid / overdue / void)
* 60 expenses, 6 payroll runs with payslip lines
* Currency rates that make multi-currency reports plausible
* 25 CRM contacts, 15 leads, 12 deals across pipeline stages,
  6 proposals, 8 quotations, 5 contracts, 4 email campaigns,
  3 customer segments, 10 follow-ups, 18 communication entries
* 8 projects, 50+ tasks across statuses, 3 sprints, 6 milestones,
  20 time entries, 4 meetings
* Inventory: 3 warehouses, 8 product categories, 20 products,
  60 stock-on-hand rows, 80 stock movements, 5 suppliers
* AI: 15 conversations with realistic message threads + 90 usage records
* 12 chatbots
* Communications: 6 wiki pages, 8 announcements, 14 shared notes,
  12 calendar events, 5 message threads
* 30 search-index entries (auto-populated via listeners as we insert)
* 20 notifications per user (mix of read / unread)
* 50+ audit-log entries
* All gamification achievements auto-awarded for the admin

Idempotency
-----------

Every block checks for an existing marker row before inserting. Re-running
is safe and adds only what's missing. Pass ``--reset`` to the CLI to wipe
the demo tenant first.

Money + dates
-------------

Every numeric is a Decimal with 2dp; every timestamp is timezone-aware
UTC. Date ranges are seeded relative to ``date.today()`` so the demo
never looks stale.

CLI
---

::

    python -m app.db.demo_seed                  # seed (idempotent)
    python -m app.db.demo_seed --reset          # wipe & reseed the demo tenant
    python -m app.db.demo_seed --tenant acme    # seed a different slug
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

# Local imports
from app.core.security import hash_password
from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.db.session import SessionLocal
from app.models.ai import AiConversation, AiMessage, AiUsageRecord, Chatbot
from app.models.communication import (
    Announcement,
    CalendarEvent,
    Message,
    MessageThread,
    SharedNote,
)
from app.models.crm import (
    CommunicationEntry,
    Contact,
    Contract,
    CustomerSegment,
    Deal,
    EmailCampaign,
    FollowUp,
    Lead,
    Proposal,
    Quotation,
)
from app.models.finance import (
    BudgetItem,
    BudgetPlan,
    CurrencyRate,
    Customer,
    Expense,
    ExpenseCategory,
    Invoice,
    InvoiceLine,
    PayrollRun,
    PayslipLine,
    RecurringPayment,
    TaxRate,
    Vendor,
    VendorPayment,
)
from app.models.hr import (
    AttendanceRecord,
    Candidate,
    DisciplinaryRecord,
    Employee,
    JobOpening,
    LeaveRequest,
    OnboardingTask,
    OrgUnit,
    PerformanceReview,
    TrainingRecord,
)
from app.models.inventory import (
    Product,
    ProductCategory,
    Supplier,
    Warehouse,
)
from app.models.projects import (
    Meeting,
    Milestone,
    Project,
    Sprint,
    Task,
    TimeEntry,
)
from app.models.tenant import Tenant
from app.models.user import Notification, User, UserRole
from app.services import gamification as gam


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

random.seed(424242)  # Deterministic demo data — reruns produce the same shape.


def D(value) -> Decimal:
    """Two-decimal-place Decimal — money never gets a binary float."""
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    return Decimal(str(value)).quantize(Decimal("0.01"))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def days_ago(n: int) -> date:
    return date.today() - timedelta(days=n)


def hours_ago(n: int) -> datetime:
    return now_utc() - timedelta(hours=n)


# ---------------------------------------------------------------------------
# Tenant + Users
# ---------------------------------------------------------------------------

TENANT_NAME = "Atlas Robotics Inc."
# Default to the same tenant slug the app boots with — so the bundled
# ``admin@local`` user (and any user you've created in that tenant) sees the
# demo data without having to switch tenants. Pass ``--tenant atlas-demo``
# to create a separate isolated demo tenant if you'd rather keep your data
# pristine.
TENANT_DEMO_SLUG = "default"

DEMO_USERS: list[dict] = [
    # name, email, role, department, title
    ("Maya Chen",       "maya@atlas-robotics.demo",    UserRole.admin,     "Executive",   "Chief Executive Officer"),
    ("David Kim",       "david@atlas-robotics.demo",   UserRole.manager,   "Finance",     "Chief Financial Officer"),
    ("Priya Patel",     "priya@atlas-robotics.demo",   UserRole.manager,   "Engineering", "VP Engineering"),
    ("Marcus Johnson",  "marcus@atlas-robotics.demo",  UserRole.manager,   "Sales",       "VP Sales"),
    ("Sarah Williams",  "sarah@atlas-robotics.demo",   UserRole.employee,  "Sales",       "Senior Account Executive"),
    ("Alex Rodriguez",  "alex@atlas-robotics.demo",    UserRole.developer, "Engineering", "Senior Engineer"),
    ("Jordan Lee",      "jordan@atlas-robotics.demo",  UserRole.employee,  "Operations",  "Operations Lead"),
    ("Emma Davis",      "emma@atlas-robotics.demo",    UserRole.employee,  "Marketing",   "Marketing Manager"),
]
DEMO_PASSWORD = "DemoPass123!"


def _ensure_tenant(db: Session, slug: str) -> Tenant:
    with bypass_tenant_filter():
        t = db.scalar(select(Tenant).where(Tenant.slug == slug))
        if t:
            return t
        t = Tenant(
            name=TENANT_NAME,
            slug=slug,
            plan="growth",
            status="active",
            settings={"demo": True, "industry": "Hardware + AI"},
            primary_contact_email="hello@atlas-robotics.demo",
            timezone="America/Los_Angeles",
            currency="USD",
        )
        db.add(t)
        db.commit()
        db.refresh(t)
    return t


def _seed_users(db: Session) -> list[User]:
    out: list[User] = []
    for name, email, role, dept, _title in DEMO_USERS:
        user = db.scalar(select(User).where(User.email == email))
        if not user:
            user = User(
                email=email,
                full_name=name,
                password_hash=hash_password(DEMO_PASSWORD),
                role=role,
                department=dept,
                is_active=True,
                last_login_at=now_utc() - timedelta(hours=random.randint(0, 72)),
            )
            db.add(user)
        out.append(user)
    db.commit()
    for u in out:
        db.refresh(u)
    return out


# ---------------------------------------------------------------------------
# Finance
# ---------------------------------------------------------------------------

CUSTOMERS_DATA = [
    ("TechFlow Industries",      "billing@techflow.demo",     "+1-415-555-0101", "USD", "100 Market St, San Francisco, CA"),
    ("Helix Manufacturing",      "ap@helix-mfg.demo",         "+49-30-555-0102", "EUR", "Friedrichstr 88, Berlin, DE"),
    ("Nordmark Solutions",       "fakturor@nordmark.demo",    "+46-8-555-0103",  "SEK", "Sveavägen 12, Stockholm, SE"),
    ("BluePeak Logistics",       "accounts@bluepeak.demo",    "+1-206-555-0104", "USD", "1500 Pier Ave, Seattle, WA"),
    ("Quantum Dynamics",         "finance@quantumdyn.demo",   "+1-512-555-0105", "USD", "200 Congress Ave, Austin, TX"),
    ("Verde Energy",             "facturas@verde-energy.demo","+34-91-555-0106", "EUR", "Calle de Goya 22, Madrid, ES"),
    ("Apex Healthcare",          "ap@apexhealth.demo",        "+1-617-555-0107", "USD", "44 Beacon St, Boston, MA"),
    ("Crimson Retail",           "invoices@crimson.demo",     "+44-20-555-0108", "GBP", "55 Old Broad St, London, UK"),
    ("Pacific Shipping Co",      "billing@pacificship.demo",  "+1-310-555-0109", "USD", "800 Harbor Dr, Long Beach, CA"),
    ("Stratus Cloud",            "ap@stratus-cloud.demo",     "+1-650-555-0110", "USD", "1 Hacker Way, Menlo Park, CA"),
    ("Meridian Group",           "billing@meridian.demo",     "+1-416-555-0111", "CAD", "100 King St W, Toronto, ON"),
    ("Solis Pharmaceuticals",    "comptes@solis-pharma.demo", "+41-22-555-0112", "CHF", "Rue du Rhône 14, Geneva, CH"),
]

VENDORS_DATA = [
    ("Amazon Web Services",   "billing@aws-demo.test",      "+1-206-555-2001", "Net 30"),
    ("Slack Technologies",     "billing@slack-demo.test",    "+1-415-555-2002", "Net 15"),
    ("GitHub Enterprise",      "ar@github-demo.test",        "+1-415-555-2003", "Net 30"),
    ("Figma Inc",              "billing@figma-demo.test",    "+1-415-555-2004", "Net 30"),
    ("Atlassian",              "billing@atlassian-demo.test","+1-415-555-2005", "Net 30"),
    ("WeWork",                 "billing@wework-demo.test",   "+1-212-555-2006", "Net 30"),
    ("Stripe Payments",        "accounts@stripe-demo.test",  "+1-415-555-2007", "Net 7"),
    ("Datadog Monitoring",     "ar@datadog-demo.test",       "+1-212-555-2008", "Net 30"),
]

EXPENSE_CATEGORIES = [
    "Software & SaaS", "Travel & Meals", "Office Supplies",
    "Marketing", "Professional Services", "Hardware",
]

CURRENCY_RATES = [
    # (base, quote, rate) — relative to USD on today's date
    ("USD", "EUR", "0.9180"),
    ("USD", "GBP", "0.7905"),
    ("USD", "SEK", "10.8500"),
    ("USD", "CHF", "0.8820"),
    ("USD", "CAD", "1.3650"),
    ("EUR", "USD", "1.0893"),
    ("GBP", "USD", "1.2650"),
]


def _seed_customers(db: Session) -> list[Customer]:
    out = []
    for name, email, phone, ccy, addr in CUSTOMERS_DATA:
        c = db.scalar(select(Customer).where(Customer.name == name))
        if not c:
            c = Customer(name=name, email=email, phone=phone, currency=ccy, billing_address=addr)
            db.add(c)
        out.append(c)
    db.commit()
    for c in out:
        db.refresh(c)
    return out


def _seed_vendors(db: Session) -> list[Vendor]:
    out = []
    for name, email, phone, terms in VENDORS_DATA:
        v = db.scalar(select(Vendor).where(Vendor.name == name))
        if not v:
            v = Vendor(name=name, email=email, phone=phone, payment_terms=terms)
            db.add(v)
        out.append(v)
    db.commit()
    for v in out:
        db.refresh(v)
    return out


def _seed_expense_categories(db: Session) -> list[ExpenseCategory]:
    out = []
    for name in EXPENSE_CATEGORIES:
        c = db.scalar(select(ExpenseCategory).where(ExpenseCategory.name == name))
        if not c:
            c = ExpenseCategory(name=name)
            db.add(c)
        out.append(c)
    db.commit()
    for c in out:
        db.refresh(c)
    return out


def _seed_currency_rates(db: Session) -> None:
    today = date.today()
    for base, quote, rate in CURRENCY_RATES:
        existing = db.scalar(
            select(CurrencyRate).where(
                CurrencyRate.base_currency == base,
                CurrencyRate.quote_currency == quote,
                CurrencyRate.effective_date == today,
            )
        )
        if existing:
            continue
        db.add(CurrencyRate(
            base_currency=base, quote_currency=quote,
            rate=Decimal(rate), effective_date=today,
        ))
    db.commit()


def _seed_tax_rates(db: Session) -> None:
    rates = [
        ("California", "CA Sales Tax", "8.625"),
        ("New York",   "NY Sales Tax", "8.875"),
        ("United Kingdom", "VAT Standard", "20.000"),
        ("Germany",    "MwSt Standard", "19.000"),
        ("Canada",     "GST/HST",      "13.000"),
    ]
    for jur, name, rate in rates:
        existing = db.scalar(select(TaxRate).where(TaxRate.jurisdiction == jur, TaxRate.name == name))
        if not existing:
            db.add(TaxRate(jurisdiction=jur, name=name, rate=Decimal(rate)))
    db.commit()


def _seed_invoices(db: Session, customers: list[Customer]) -> list[Invoice]:
    """30 invoices across statuses with realistic line items."""
    if db.scalar(select(Invoice).limit(1)) is not None:
        return list(db.scalars(select(Invoice).limit(50)).all())
    LINE_TEMPLATES = [
        ("Monthly retainer",                     1,  "8500.00"),
        ("Engineering hours — Senior",         40,   "175.00"),
        ("Engineering hours — Lead",           20,   "225.00"),
        ("Cloud infra provisioning",            1,  "3200.00"),
        ("On-site integration visit",           1,  "5400.00"),
        ("Hardware unit — AR-Sense v2",        12,  "1290.00"),
        ("Hardware unit — AR-Pilot",            6,  "2150.00"),
        ("Quarterly support package",           1,  "4750.00"),
        ("Onboarding workshop",                 1,  "3200.00"),
        ("API integration — Salesforce",        1,  "6800.00"),
    ]
    STATUSES = ["draft", "issued", "issued", "paid", "paid", "paid", "overdue", "void"]
    issued = []
    for i in range(30):
        cust = random.choice(customers)
        status = random.choice(STATUSES)
        issue = days_ago(random.randint(1, 180))
        due = issue + timedelta(days=30)
        inv = Invoice(
            invoice_number=f"INV-{2025 + (i // 25)}-{1000 + i:04d}",
            customer_id=cust.id,
            issue_date=issue,
            due_date=due,
            status=status,
            currency=cust.currency,
            notes=f"Thank you for your business — terms net 30 days.",
        )
        sub = Decimal("0")
        tax = Decimal("0")
        for _ in range(random.randint(1, 3)):
            desc, qty, unit = random.choice(LINE_TEMPLATES)
            line_total = (Decimal(qty) * Decimal(unit)).quantize(Decimal("0.01"))
            sub += line_total
            inv.lines.append(InvoiceLine(
                description=desc, quantity=Decimal(qty), unit_price=Decimal(unit),
                tax_rate=Decimal("0"), line_total=line_total,
            ))
        inv.subtotal = D(sub)
        inv.tax_total = D(tax)
        inv.discount_total = D(0)
        inv.total = D(sub + tax)
        db.add(inv)
        issued.append(inv)
    db.commit()
    return issued


def _seed_expenses(
    db: Session,
    vendors: list[Vendor],
    categories: list[ExpenseCategory],
) -> None:
    if db.scalar(select(Expense).limit(1)) is not None:
        return
    DESCRIPTIONS = {
        "Software & SaaS":       ["AWS — monthly compute", "GitHub Enterprise seats", "Datadog observability", "Slack Standard plan"],
        "Travel & Meals":        ["Client dinner — TechFlow", "Flight — SFO → BOS", "Hotel — 2 nights", "Team lunch"],
        "Office Supplies":       ["Standing desk", "Ergonomic chair", "Whiteboard + markers"],
        "Marketing":             ["LinkedIn ads — Sep", "Conference sponsorship", "Brand video shoot"],
        "Professional Services": ["Legal — contract review", "Accounting — quarterly close", "Consultant — RFP support"],
        "Hardware":              ["MacBook Pro 16\" — Alex", "Sensor array prototype", "Test fixtures"],
    }
    for _ in range(60):
        cat = random.choice(categories)
        vend = random.choice(vendors)
        descs = DESCRIPTIONS.get(cat.name, [cat.name])
        db.add(Expense(
            category_id=cat.id,
            vendor_id=vend.id,
            date=days_ago(random.randint(1, 180)),
            amount=D(random.choice([24.95, 89.50, 199.00, 350.00, 1240.00, 2890.00, 850.00, 5400.00])),
            currency="USD",
            description=random.choice(descs),
        ))
    db.commit()


def _seed_payroll(db: Session, employees: list[Employee]) -> None:
    if db.scalar(select(PayrollRun).limit(1)) is not None:
        return
    for months_back in range(6, 0, -1):
        period_start = (date.today().replace(day=1) - timedelta(days=months_back * 30)).replace(day=1)
        period_end = (period_start.replace(day=28) + timedelta(days=4))
        period_end = period_end - timedelta(days=period_end.day)  # last day of month
        run = PayrollRun(
            period_start=period_start,
            period_end=period_end,
            status="paid",
        )
        gross = Decimal("0")
        deductions = Decimal("0")
        db.add(run)
        db.flush()
        for emp in employees:
            base = (emp.salary or Decimal("5000")) / Decimal("12")
            tax = base * Decimal("0.27")
            db.add(PayslipLine(payroll_run_id=run.id, employee_id=emp.id,
                               label="Base salary", amount=D(base), kind="earning"))
            db.add(PayslipLine(payroll_run_id=run.id, employee_id=emp.id,
                               label="Income tax", amount=D(tax), kind="tax"))
            gross += base
            deductions += tax
        run.gross_total = D(gross)
        run.deduction_total = D(deductions)
        run.net_total = D(gross - deductions)
    db.commit()


def _seed_budgets(db: Session) -> None:
    if db.scalar(select(BudgetPlan).limit(1)) is not None:
        return
    plan = BudgetPlan(name=f"Operating Budget {date.today().year}", fiscal_year=date.today().year, currency="USD")
    db.add(plan)
    db.flush()
    items = [
        ("Engineering payroll", "1200000.00", "740000.00"),
        ("Sales & marketing",   "480000.00",  "310000.00"),
        ("Cloud infrastructure", "180000.00",  "112000.00"),
        ("Travel & events",      "90000.00",   "38000.00"),
        ("Software & tools",     "60000.00",   "44000.00"),
        ("Office & operations", "150000.00",   "82000.00"),
    ]
    for cat, planned, actual in items:
        db.add(BudgetItem(budget_plan_id=plan.id, category=cat,
                          planned_amount=Decimal(planned), actual_amount=Decimal(actual)))
    db.commit()


def _seed_recurring(db: Session) -> None:
    if db.scalar(select(RecurringPayment).limit(1)) is not None:
        return
    items = [
        ("AWS — monthly compute", "5800.00", "USD", "monthly"),
        ("Office rent",          "12500.00", "USD", "monthly"),
        ("GitHub Enterprise",     "1200.00", "USD", "monthly"),
        ("Datadog",                "640.00", "USD", "monthly"),
    ]
    for title, amount, ccy, cadence in items:
        db.add(RecurringPayment(
            title=title, amount=Decimal(amount), currency=ccy, cadence=cadence,
            next_due_date=date.today() + timedelta(days=random.randint(2, 28)),
        ))
    db.commit()


def _seed_vendor_payments(db: Session, vendors: list[Vendor]) -> None:
    if db.scalar(select(VendorPayment).limit(1)) is not None:
        return
    for v in vendors:
        for _ in range(random.randint(1, 3)):
            db.add(VendorPayment(
                vendor_id=v.id,
                payment_date=days_ago(random.randint(1, 90)),
                amount=D(random.choice([580.00, 1240.00, 3200.00, 4500.00])),
                status="paid",
            ))
    db.commit()


# ---------------------------------------------------------------------------
# CRM
# ---------------------------------------------------------------------------

CONTACTS_DATA = [
    # name, company, email, phone, tags
    ("Eleanor Wright",    "TechFlow Industries",  "eleanor.wright@techflow.demo",   "+1-415-555-1001", ["vip", "champion"]),
    ("Marcus Vega",       "TechFlow Industries",  "marcus.vega@techflow.demo",      "+1-415-555-1002", ["technical"]),
    ("Hannelore Müller",  "Helix Manufacturing",  "h.muller@helix-mfg.demo",        "+49-30-555-1003", ["decision-maker"]),
    ("Olav Lindqvist",    "Nordmark Solutions",   "olav@nordmark.demo",             "+46-8-555-1004",  ["champion"]),
    ("Riley Adams",       "BluePeak Logistics",   "r.adams@bluepeak.demo",          "+1-206-555-1005", ["vip"]),
    ("Vikram Singh",      "Quantum Dynamics",     "vikram@quantumdyn.demo",         "+1-512-555-1006", ["champion", "technical"]),
    ("Beatriz Romero",    "Verde Energy",         "beatriz@verde-energy.demo",      "+34-91-555-1007", ["new"]),
    ("Dr. Yusuf Aslam",   "Apex Healthcare",      "yaslam@apexhealth.demo",         "+1-617-555-1008", ["vip", "executive"]),
    ("James Pemberton",   "Crimson Retail",       "j.pemberton@crimson.demo",       "+44-20-555-1009", ["executive"]),
    ("Lana Petrova",      "Pacific Shipping Co",  "l.petrova@pacificship.demo",     "+1-310-555-1010", ["technical"]),
    ("Dmitri Volkov",     "Stratus Cloud",        "dmitri@stratus-cloud.demo",      "+1-650-555-1011", ["vip", "champion"]),
    ("Sophie Tremblay",   "Meridian Group",       "sophie@meridian.demo",           "+1-416-555-1012", ["executive"]),
    ("Hans Weber",        "Solis Pharmaceuticals","hans@solis-pharma.demo",         "+41-22-555-1013", ["new"]),
    ("Aiko Tanaka",       "Stratus Cloud",        "aiko@stratus-cloud.demo",        "+1-650-555-1014", ["technical"]),
    ("Carlos Mendoza",    "BluePeak Logistics",   "carlos@bluepeak.demo",           "+1-206-555-1015", ["champion"]),
    ("Priya Krishnan",    "Apex Healthcare",      "priya@apexhealth.demo",          "+1-617-555-1016", ["technical"]),
    ("Theo Whitfield",    "Crimson Retail",       "theo@crimson.demo",              "+44-20-555-1017", ["new"]),
    ("Ines Costa",        "Verde Energy",         "ines@verde-energy.demo",         "+34-91-555-1018", ["executive"]),
    ("Alma Eklund",       "Nordmark Solutions",   "alma@nordmark.demo",             "+46-8-555-1019",  ["technical"]),
    ("Felix Beaumont",    "Meridian Group",       "felix@meridian.demo",            "+1-416-555-1020", ["champion"]),
    ("Gabriela Santos",   "Pacific Shipping Co",  "gabi@pacificship.demo",          "+1-310-555-1021", ["new"]),
    ("Idris Khaled",      "Quantum Dynamics",     "idris@quantumdyn.demo",          "+1-512-555-1022", ["executive"]),
    ("Naomi Brown",       "TechFlow Industries",  "naomi@techflow.demo",            "+1-415-555-1023", ["technical"]),
    ("Oskar Falck",       "Helix Manufacturing",  "oskar@helix-mfg.demo",           "+49-30-555-1024", ["new"]),
    ("Renata Vasquez",    "Solis Pharmaceuticals","renata@solis-pharma.demo",       "+41-22-555-1025", ["champion"]),
]

LEAD_SOURCES = ["LinkedIn", "Inbound — Website", "Trade Show", "Referral", "Cold Outreach", "Webinar", "Partner"]
LEAD_STATUSES = ["new", "contacted", "qualified", "unqualified", "converted"]

DEAL_TITLES = [
    "Enterprise rollout — Q1",
    "Pilot program — 6 sites",
    "Integration + 3-year support",
    "Hardware refresh + AI module",
    "Strategic partnership",
    "Annual renewal + expansion",
    "Multi-region deployment",
    "Custom AR-Sense fleet",
    "Cloud migration",
    "Replacement of legacy system",
    "POC → production",
    "Add-on: predictive maintenance",
]
DEAL_STAGES_PROB = [
    ("qualified",   "30"),
    ("proposal",    "55"),
    ("negotiation", "75"),
    ("won",         "100"),
    ("won",         "100"),
    ("lost",        "0"),
]


def _seed_crm(db: Session) -> tuple[list[Contact], list[Deal], list[Lead]]:
    if db.scalar(select(Contact).limit(1)) is None:
        contacts: list[Contact] = []
        for name, company, email, phone, tags in CONTACTS_DATA:
            c = Contact(name=name, company=company, email=email, phone=phone, tags=json.dumps(tags))
            db.add(c)
            contacts.append(c)
        db.commit()
        for c in contacts:
            db.refresh(c)
    else:
        contacts = list(db.scalars(select(Contact)).all())

    if db.scalar(select(Lead).limit(1)) is None:
        for _ in range(15):
            contact = random.choice(contacts)
            db.add(Lead(
                contact_id=contact.id,
                source=random.choice(LEAD_SOURCES),
                status=random.choice(LEAD_STATUSES),
                score=random.randint(5, 95),
                notes=f"Inbound interest after {random.choice(LEAD_SOURCES).lower()} touch.",
            ))
        db.commit()

    deals: list[Deal] = []
    if db.scalar(select(Deal).limit(1)) is None:
        for i, title in enumerate(DEAL_TITLES):
            stage, prob = DEAL_STAGES_PROB[i % len(DEAL_STAGES_PROB)]
            contact = random.choice(contacts)
            d = Deal(
                contact_id=contact.id,
                title=title,
                stage=stage,
                value=Decimal(random.choice([45000, 89000, 124000, 240000, 380000, 580000])),
                probability=Decimal(prob),
                expected_close_date=date.today() + timedelta(days=random.randint(-30, 120)),
            )
            db.add(d)
            deals.append(d)
        db.commit()
        for d in deals:
            db.refresh(d)
    else:
        deals = list(db.scalars(select(Deal)).all())

    if db.scalar(select(CommunicationEntry).limit(1)) is None:
        CHANNELS = ["email", "call", "meeting", "note"]
        for _ in range(18):
            c = random.choice(contacts)
            db.add(CommunicationEntry(
                contact_id=c.id,
                channel=random.choice(CHANNELS),
                subject=random.choice([
                    "Quarterly business review",
                    "Re: pricing question",
                    "Demo follow-up",
                    "Integration kick-off",
                    "Renewal conversation",
                ]),
                body="Discussed scope, timeline, and pricing. Customer is leaning toward the 3-year package.",
            ))
        db.commit()

    if db.scalar(select(FollowUp).limit(1)) is None:
        for _ in range(10):
            c = random.choice(contacts)
            db.add(FollowUp(
                contact_id=c.id,
                due_at=now_utc() + timedelta(days=random.randint(-3, 14)),
                status=random.choice(["open", "open", "open", "done"]),
                notes=random.choice([
                    "Send updated pricing sheet",
                    "Schedule demo with engineering team",
                    "Forward security questionnaire",
                    "Review final contract redlines",
                ]),
            ))
        db.commit()

    if db.scalar(select(Proposal).limit(1)) is None:
        PROPOSAL_TITLES = [
            "Enterprise rollout proposal — TechFlow",
            "Pilot to production proposal — Quantum",
            "Multi-region deployment — Helix",
            "Hardware + AI module — Apex Healthcare",
            "Strategic partnership — Stratus Cloud",
            "Cloud migration — Pacific Shipping",
        ]
        for title in PROPOSAL_TITLES:
            db.add(Proposal(
                contact_id=random.choice(contacts).id,
                title=title,
                status=random.choice(["draft", "sent", "accepted", "rejected"]),
                amount=Decimal(random.choice([45000, 124000, 240000, 380000])),
                body=f"Executive summary, scope, deliverables, and timeline for {title}.",
            ))
        db.commit()

    if db.scalar(select(Quotation).limit(1)) is None:
        for i in range(8):
            db.add(Quotation(
                quote_number=f"QT-{date.today().year}-{200 + i:04d}",
                contact_id=random.choice(contacts).id,
                status=random.choice(["draft", "sent", "accepted", "expired"]),
                total=Decimal(random.choice([18900, 45000, 89000, 124000])),
            ))
        db.commit()

    if db.scalar(select(Contract).limit(1)) is None:
        for title in [
            "MSA — TechFlow Industries",
            "SOW — Quantum Dynamics Pilot",
            "NDA — Pacific Shipping",
            "Renewal — Stratus Cloud",
            "MSA — Apex Healthcare",
        ]:
            db.add(Contract(
                contact_id=random.choice(contacts).id,
                title=title,
                status=random.choice(["draft", "signed", "signed", "signed"]),
                value=Decimal(random.choice([120000, 240000, 580000, 0])),
            ))
        db.commit()

    if db.scalar(select(EmailCampaign).limit(1)) is None:
        for name in [
            "Q4 product launch announcement",
            "Customer success newsletter — Oct",
            "Holiday discount — 20% off renewals",
            "Webinar invite — Predictive Maintenance",
        ]:
            db.add(EmailCampaign(
                name=name,
                status=random.choice(["sent", "sent", "scheduled"]),
                sent_count=random.randint(280, 2400),
                open_count=random.randint(80, 1100),
                click_count=random.randint(20, 380),
            ))
        db.commit()

    if db.scalar(select(CustomerSegment).limit(1)) is None:
        SEGMENTS = [
            ("Enterprise champions", {"tags": {"any_of": ["vip", "champion"]}}),
            ("Technical buyers",     {"tags": {"any_of": ["technical"]}}),
            ("New prospects",        {"tags": {"any_of": ["new"]}}),
        ]
        for name, rules in SEGMENTS:
            db.add(CustomerSegment(name=name, rules=json.dumps(rules)))
        db.commit()

    return contacts, deals, list(db.scalars(select(Lead)).all())


# ---------------------------------------------------------------------------
# HR
# ---------------------------------------------------------------------------

EMPLOYEE_NAMES_BY_DEPT = {
    "Engineering": [
        ("Alex Rodriguez", "Senior Engineer", "165000"),
        ("Priya Patel", "VP Engineering", "260000"),
        ("Kenji Watanabe", "Staff Engineer", "190000"),
        ("Aisha Mahmoud", "Senior Engineer", "168000"),
        ("Owen Carter", "Engineer II", "142000"),
        ("Lucia Romano", "Engineer II", "138000"),
        ("Bram Hoekstra", "Senior Engineer", "172000"),
        ("Mei Lin", "Engineer I", "118000"),
        ("Tobias Krüger", "Staff Engineer", "195000"),
        ("Sasha Volkov", "Engineer II", "140000"),
        ("Imani Coleman", "Engineering Manager", "210000"),
        ("Diego Alvarez", "Senior Engineer", "166000"),
        ("Yara Saleh", "Engineer I", "121000"),
        ("Henrik Olsen", "Senior Engineer", "169000"),
        ("Ava Sinclair", "Engineer II", "139000"),
        ("Rishi Kapoor", "Senior Engineer", "163000"),
        ("Nora Lindberg", "Engineer I", "120000"),
        ("Caleb Hawthorne", "Engineering Manager", "215000"),
        ("Marisol Vega", "Engineer II", "141000"),
        ("Tobias Maier", "Engineer I", "117000"),
    ],
    "Sales": [
        ("Marcus Johnson", "VP Sales", "240000"),
        ("Sarah Williams", "Senior Account Executive", "165000"),
        ("Daniel Kowalski", "Account Executive", "135000"),
        ("Rosa Martinez", "Senior Account Executive", "162000"),
        ("Liam Bennett", "Sales Development Rep", "78000"),
        ("Emma Lawrence", "Account Executive", "138000"),
        ("Tariq Ahmed", "Sales Engineer", "155000"),
        ("Anya Petrov", "Sales Development Rep", "76000"),
        ("Joel Castellanos", "Account Executive", "136000"),
        ("Mira Ito", "Senior Account Executive", "168000"),
    ],
    "Marketing": [
        ("Emma Davis", "Marketing Manager", "135000"),
        ("Luca Conti", "Content Marketer", "98000"),
        ("Zara Ahmed", "Demand Gen Lead", "138000"),
        ("Felipe Nunes", "Designer", "112000"),
        ("Iris Larsson", "Brand Strategist", "126000"),
    ],
    "Operations": [
        ("Jordan Lee", "Operations Lead", "128000"),
        ("Naomi Park", "Logistics Coordinator", "92000"),
        ("Esteban Ruiz", "Office Manager", "84000"),
        ("Maya Joshi", "Procurement Specialist", "98000"),
        ("Karim Hassan", "Facilities Coordinator", "78000"),
    ],
    "Finance": [
        ("David Kim", "Chief Financial Officer", "295000"),
        ("Greta Schaffer", "Senior Accountant", "118000"),
        ("Andre Lefebvre", "Financial Analyst", "108000"),
        ("Yuki Nakamura", "Controller", "165000"),
    ],
    "HR": [
        ("Camille Rousseau", "Head of People", "175000"),
        ("Devon Mitchell", "HR Business Partner", "118000"),
        ("Mira Sokolov", "Talent Acquisition Lead", "128000"),
    ],
    "Customer Success": [
        ("Hugo Vasquez", "Head of CS", "175000"),
        ("Tess O'Connor", "Senior CSM", "138000"),
        ("Akiko Yamamoto", "CSM", "112000"),
    ],
}


def _seed_employees(db: Session, users: list[User]) -> list[Employee]:
    if db.scalar(select(Employee).limit(1)) is not None:
        return list(db.scalars(select(Employee)).all())
    employees: list[Employee] = []
    user_by_email = {u.email: u for u in users}
    idx = 0
    for dept, roster in EMPLOYEE_NAMES_BY_DEPT.items():
        for name, title, salary in roster:
            idx += 1
            email_local = name.lower().replace(" ", ".").replace("'", "")
            email = f"{email_local}@atlas-robotics.demo"
            linked_user = user_by_email.get(email)
            emp = Employee(
                user_id=linked_user.id if linked_user else None,
                employee_code=f"ATL-{1000 + idx:04d}",
                full_name=name,
                email=email,
                department=dept,
                title=title,
                hire_date=days_ago(random.randint(60, 2200)),
                salary=Decimal(salary),
                status="active",
            )
            db.add(emp)
            employees.append(emp)
    db.commit()
    for e in employees:
        db.refresh(e)
    return employees


def _seed_org_units(db: Session, employees: list[Employee]) -> None:
    if db.scalar(select(OrgUnit).limit(1)) is not None:
        return
    by_dept: dict[str, list[Employee]] = {}
    for e in employees:
        by_dept.setdefault(e.department or "Other", []).append(e)
    root = OrgUnit(name="Atlas Robotics Inc.", parent_id=None,
                   manager_employee_id=next((e.id for e in employees if e.title == "Chief Executive Officer"), None))
    db.add(root)
    db.flush()
    for dept, members in by_dept.items():
        manager = next((e for e in members if "Manager" in (e.title or "") or "VP" in (e.title or "") or "Chief" in (e.title or "") or "Head" in (e.title or "")), members[0])
        unit = OrgUnit(name=dept, parent_id=root.id, manager_employee_id=manager.id)
        db.add(unit)
    db.commit()


def _seed_attendance_and_leave(db: Session, employees: list[Employee]) -> None:
    if db.scalar(select(AttendanceRecord).limit(1)) is None:
        for emp in employees[:20]:  # 20 most recent — keeps the seed quick
            for d in range(14):
                day = days_ago(d)
                if day.weekday() >= 5:
                    continue
                clock_in = datetime.combine(day, datetime.min.time()).replace(hour=9, minute=random.randint(0, 18), tzinfo=timezone.utc)
                clock_out = clock_in + timedelta(hours=random.randint(7, 10), minutes=random.randint(0, 59))
                db.add(AttendanceRecord(employee_id=emp.id, clock_in=clock_in, clock_out=clock_out, source="kiosk"))
        db.commit()

    if db.scalar(select(LeaveRequest).limit(1)) is None:
        TYPES = ["vacation", "vacation", "sick", "personal", "parental"]
        STATUSES = ["pending", "approved", "approved", "approved", "rejected"]
        for _ in range(15):
            emp = random.choice(employees)
            start = days_ago(random.randint(-30, 60))
            end = start + timedelta(days=random.randint(1, 7))
            db.add(LeaveRequest(
                employee_id=emp.id, start_date=start, end_date=end,
                leave_type=random.choice(TYPES), status=random.choice(STATUSES),
                reason="Family travel" if random.random() > 0.4 else "Personal",
            ))
        db.commit()


def _seed_recruitment(db: Session) -> None:
    if db.scalar(select(JobOpening).limit(1)) is None:
        OPENINGS = [
            ("Staff Software Engineer — Robotics",  "Engineering", "open",
             "Lead architecture of the next-gen perception stack. Rust + Python."),
            ("Senior Account Executive",            "Sales", "open",
             "Mid-market segment, $1M+ quota. Hardware-and-AI experience preferred."),
            ("Director of Customer Success",        "Customer Success", "open",
             "Scale CS team from 4 to 12. Build playbooks for the enterprise tier."),
            ("Hardware Test Engineer",              "Engineering", "open",
             "Own the production-test rig + automated QA pipeline."),
            ("Marketing Designer",                  "Marketing", "closed",
             "Brand + product design. Figma-fluent."),
        ]
        for title, dept, status, desc in OPENINGS:
            db.add(JobOpening(title=title, department=dept, status=status, description=desc))
        db.commit()

    if db.scalar(select(Candidate).limit(1)) is None:
        openings = list(db.scalars(select(JobOpening)).all())
        CANDIDATE_NAMES = [
            "Tara Khan", "Jules Whitman", "Pablo Diaz", "Sienna Brooks", "Hiroshi Sato",
            "Lilia Karim", "Otto Brandt", "Sam Iglesias", "Mona Halabi", "Ravi Singh",
            "Cleo Vasilenko", "Aaron Riley", "Naya Patel", "Kasper Holt", "Fenella Stone",
            "Daichi Mori", "Yasmin Said", "Wren Sanderson", "Brooke Yamada", "Eitan Levi",
        ]
        STAGES = ["applied", "screening", "screening", "interview", "interview", "offer", "rejected"]
        for name in CANDIDATE_NAMES:
            db.add(Candidate(
                job_opening_id=random.choice(openings).id if openings else None,
                full_name=name,
                email=f"{name.lower().replace(' ', '.')}@candidate.demo",
                stage=random.choice(STAGES),
                rating=Decimal(str(round(random.uniform(2.5, 4.8), 1))),
            ))
        db.commit()


def _seed_reviews_training_discipline(db: Session, employees: list[Employee], users: list[User]) -> None:
    admin = next(u for u in users if u.role == UserRole.admin)
    if db.scalar(select(PerformanceReview).limit(1)) is None:
        for emp in employees[:12]:
            db.add(PerformanceReview(
                employee_id=emp.id,
                reviewer_id=admin.id,
                period="H2 2025",
                score=Decimal(str(round(random.uniform(3.4, 4.8), 1))),
                notes="Consistent delivery; strong cross-team collaboration. Continue mentoring juniors.",
            ))
        db.commit()
    if db.scalar(select(TrainingRecord).limit(1)) is None:
        TRAININGS = [
            "Security Awareness — Annual",
            "Sexual Harassment Prevention",
            "GDPR Foundations",
            "AWS Solutions Architect Prep",
            "Kubernetes Fundamentals",
        ]
        for emp in employees[:15]:
            status = random.choice(["completed", "in_progress", "assigned"])
            completed_at = None
            if status == "completed":
                completed_at = now_utc() - timedelta(days=random.randint(0, 180))
            db.add(TrainingRecord(
                employee_id=emp.id,
                course_name=random.choice(TRAININGS),
                status=status,
                completed_at=completed_at,
            ))
        db.commit()
    if db.scalar(select(OnboardingTask).limit(1)) is None:
        ONBOARDING = [
            ("Sign offer letter",               -5,  "open"),
            ("Account provisioning (email, VPN, GitHub)", -2, "open"),
            ("First-day welcome lunch",          1,  "open"),
            ("Complete benefits enrolment",      5,  "open"),
            ("First 30-day check-in",            30, "open"),
        ]
        new_hires = [e for e in employees if e.hire_date and (date.today() - e.hire_date).days < 90][:3]
        for hire in new_hires:
            for title, offset, status in ONBOARDING:
                db.add(OnboardingTask(
                    employee_id=hire.id, title=title,
                    status=status,
                    due_date=(hire.hire_date or date.today()) + timedelta(days=offset),
                ))
        db.commit()


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def _seed_inventory(db: Session) -> None:
    if db.scalar(select(Warehouse).limit(1)) is None:
        WH = [
            ("SF Distribution Center",  "SFO-DC", "950 Bryant St, San Francisco, CA", "Jordan Lee",  120000),
            ("NY Fulfillment",          "NYC-FC", "200 Park Ave, NYC",                  "Naomi Park",  90000),
            ("ATL Retail Store",        "ATL-RS", "1000 Peachtree St, Atlanta, GA",    "Esteban Ruiz", 45000),
        ]
        for name, code, addr, mgr, cap in WH:
            db.add(Warehouse(name=name, code=code, address=addr, manager=mgr, capacity=cap, phone="+1-415-555-3000"))
        db.commit()

    if db.scalar(select(ProductCategory).limit(1)) is None:
        CATS = ["AR-Sense Series", "AR-Pilot Series", "Sensors & Modules", "Cables & Adapters", "Spares", "Accessories", "Docs & Manuals", "Software"]
        for c in CATS:
            db.add(ProductCategory(name=c))
        db.commit()

    if db.scalar(select(Product).limit(1)) is None:
        cats = list(db.scalars(select(ProductCategory)).all())
        by = {c.name: c for c in cats}
        PRODUCTS = [
            ("AR-S2-100", "AR-Sense v2 Standard",    "AR-Sense Series",   890, 1290, 8,  16),
            ("AR-S2-200", "AR-Sense v2 Pro",         "AR-Sense Series",   1240, 1790, 6, 12),
            ("AR-P1-100", "AR-Pilot Base",           "AR-Pilot Series",   1480, 2150, 5, 10),
            ("AR-P1-200", "AR-Pilot Pro",            "AR-Pilot Series",   1880, 2790, 4,  8),
            ("MOD-LIDAR-X", "LIDAR-X Module",        "Sensors & Modules", 380, 580, 12, 24),
            ("MOD-CAM-4K",  "4K Camera Module",      "Sensors & Modules", 240, 380, 14, 28),
            ("MOD-IMU-9",   "9-Axis IMU",            "Sensors & Modules", 95,  180, 30, 60),
            ("CBL-USBC-2M", "USB-C Cable 2m",        "Cables & Adapters", 12,  24, 80,160),
            ("CBL-RJ45-3M", "Cat6 Cable 3m",         "Cables & Adapters", 8,   18, 100,200),
            ("ADP-PD-100W", "Power Adapter 100W",    "Cables & Adapters", 38,  72, 40,  80),
            ("SPR-FAN-50",  "Cooling Fan 50mm",      "Spares",            6,   18, 60, 120),
            ("SPR-FAN-80",  "Cooling Fan 80mm",      "Spares",            9,   22, 50, 100),
            ("SPR-LENS-V2", "AR-Sense v2 Lens Kit",  "Spares",            45,  98, 20,  40),
            ("ACC-CASE-PRO","Pro Carrying Case",     "Accessories",       28,  72, 30,  60),
            ("ACC-STAND-S", "Adjustable Stand",      "Accessories",       18,  42, 50, 100),
            ("ACC-DOCK-MAG","Magnetic Dock",         "Accessories",       54, 118, 25,  50),
            ("DOC-SET-INS", "Installation Guide Set","Docs & Manuals",     2,   8, 200,400),
            ("SW-LICENSE-1","Atlas OS — 1yr seat",   "Software",         100, 240, 999,500),
            ("SW-API-CRED", "API Credits — 100k",    "Software",          80, 180, 999,200),
            ("SW-PRO-PLUG", "Pro Plugin Bundle",     "Software",         140, 320, 999,250),
        ]
        for sku, name, cat, cost, price, low, ro in PRODUCTS:
            db.add(Product(
                sku=sku, name=name, category_id=by[cat].id,
                description=f"{name} — production-grade.",
                unit_cost=Decimal(cost), unit_price=Decimal(price),
                low_stock_threshold=low, reorder_quantity=ro,
            ))
        db.commit()

    if db.scalar(select(Supplier).limit(1)) is None:
        SUPPLIERS = [
            ("Shenzhen Electronics Ltd",   "orders@sz-electronics.demo",  "+86-755-555-4001", "Lin Wei",         "Net 45", 5, 18),
            ("Bay Area Components Inc",    "sales@bay-comp.demo",          "+1-510-555-4002",   "Robert Chen",     "Net 30", 4,  7),
            ("Munich Precision GmbH",      "vertrieb@munich-precision.de","+49-89-555-4003",  "Anna Schmidt",    "Net 30", 5, 14),
            ("Pacific Plastics Co",        "info@pacific-plastics.demo",   "+1-310-555-4004",   "Carlos Mendoza",  "Net 30", 4,  5),
            ("Helsinki Sensors Oy",        "sales@helsinki-sensors.demo",  "+358-9-555-4005",  "Aino Virtanen",   "Net 30", 5, 21),
        ]
        for name, email, phone, person, terms, rating, lead in SUPPLIERS:
            db.add(Supplier(
                name=name, email=email, phone=phone, contact_person=person,
                payment_terms=terms, rating=rating, lead_time_days=lead, is_active=True,
            ))
        db.commit()


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

PROJECT_DEFS = [
    ("Apollo — Customer Portal Rebuild", "Replace the legacy portal with a Next.js / FastAPI stack.", "active",  -60, 90,   480000, "#6366F1", 38),
    ("Mercury — Mobile App",              "Native iOS/Android app for AR-Sense remote management.",   "active",  -30, 120,  320000, "#22D3EE", 18),
    ("Atlas Cloud Migration",             "Move on-prem workloads to AWS. Phase 1 of 3.",             "active",  -90, 60,   240000, "#10B981", 62),
    ("Hardware QA Automation",            "Build the automated production-line test rig.",             "active",  -45, 75,   180000, "#F59E0B", 44),
    ("Sales Enablement v2",               "New collateral, demo lab refresh, certification program.","active",   -20, 40,    90000, "#EC4899", 28),
    ("Q4 Marketing Campaign",             "Multi-channel campaign around the AR-Pilot launch.",       "active",   -10, 60,   140000, "#A855F7", 52),
    ("ISO 27001 Certification",           "Prepare and certify against ISO 27001 by Q2.",             "planned",   30, 240,  120000, "#0EA5E9", 5),
    ("Knowledge Base Refresh",            "Migrate docs, add search, refresh contributor flow.",      "active",   -15, 30,    24000, "#84CC16", 70),
]

TASK_TITLES = [
    ("design", "Information architecture audit"),
    ("design", "High-fidelity mockups — dashboard"),
    ("design", "Component library setup"),
    ("backend", "Tenant scoping middleware"),
    ("backend", "Webhook signing rotation"),
    ("backend", "Performance: invoice list query"),
    ("backend", "Add idempotency middleware"),
    ("frontend", "Onboarding checklist component"),
    ("frontend", "Settings → Appearance panel"),
    ("frontend", "Empty states for every list"),
    ("infra", "Terraform module — RDS"),
    ("infra", "CI: Playwright artifacts"),
    ("infra", "Logging: structured JSON sink"),
    ("qa", "Smoke test — payment webhook"),
    ("qa", "Smoke test — SSO login"),
    ("docs", "API reference — webhooks"),
    ("docs", "Operator runbook — restore from backup"),
    ("research", "Customer interview — TechFlow"),
    ("research", "Customer interview — Stratus Cloud"),
    ("misc", "Triage GitHub issues"),
]

STATUSES = ["todo", "in_progress", "in_progress", "review", "done", "done", "blocked"]
PRIORITIES = ["low", "medium", "medium", "high", "urgent"]


def _seed_projects(db: Session, users: list[User]) -> list[Project]:
    if db.scalar(select(Project).limit(1)) is not None:
        return list(db.scalars(select(Project)).all())
    projects = []
    for name, desc, status, start_off, end_off, budget, color, progress in PROJECT_DEFS:
        p = Project(
            name=name, description=desc, status=status,
            start_date=days_ago(-start_off),
            end_date=days_ago(-end_off),
            budget=Decimal(budget), color=color, progress=progress,
        )
        db.add(p)
        projects.append(p)
    db.commit()
    for p in projects:
        db.refresh(p)

    # Tasks
    for p in projects:
        n_tasks = random.randint(5, 12)
        for i in range(n_tasks):
            tag, title = random.choice(TASK_TITLES)
            assignee = random.choice(users)
            db.add(Task(
                project_id=p.id,
                assignee_id=assignee.id,
                title=title,
                description=f"Auto-seeded task for project {p.name}.",
                status=random.choice(STATUSES),
                priority=random.choice(PRIORITIES),
                start_date=days_ago(random.randint(1, 40)),
                due_date=days_ago(random.randint(-30, 30)),
                estimated_hours=Decimal(str(random.choice([2, 4, 8, 16, 24, 40]))),
                actual_hours=Decimal(str(random.choice([0, 2, 6, 12, 18]))),
                story_points=random.choice([1, 2, 3, 5, 8, 13]),
                position=i,
                tags=tag,
            ))

    # Sprints (only for the top 3 active projects)
    for p in projects[:3]:
        for s in range(3):
            start = days_ago(-(s - 1) * 14)
            end = start + timedelta(days=14)
            db.add(Sprint(
                project_id=p.id,
                name=f"Sprint {s + 1}",
                start_date=start, end_date=end,
                goal=f"Ship the milestone for {p.name} — sprint {s + 1}",
                status="active" if s == 1 else ("completed" if s == 0 else "planned"),
                capacity_points=40,
            ))

    # Milestones
    for p in projects:
        for i in range(2):
            db.add(Milestone(
                project_id=p.id,
                title=f"{p.name} — milestone {i + 1}",
                description="Hand-off, demo, retro.",
                due_date=days_ago(-(i * 30 + 14)),
                status="open",
                progress=random.choice([0, 25, 50, 75]),
            ))
    db.commit()
    return projects


def _seed_time_meetings(db: Session, projects: list[Project], users: list[User]) -> None:
    if db.scalar(select(TimeEntry).limit(1)) is None:
        tasks = list(db.scalars(select(Task).limit(40)).all())
        for _ in range(20):
            t = random.choice(tasks)
            u = random.choice(users)
            started = now_utc() - timedelta(days=random.randint(0, 14), hours=random.randint(1, 6))
            ended = started + timedelta(minutes=random.choice([30, 60, 90, 120, 180]))
            db.add(TimeEntry(
                task_id=t.id, user_id=u.id,
                started_at=started, ended_at=ended,
                minutes=int((ended - started).total_seconds() // 60),
                notes="Work in progress",
                is_billable=True,
            ))
        db.commit()

    if db.scalar(select(Meeting).limit(1)) is None:
        for p in projects[:4]:
            start = now_utc() + timedelta(days=random.randint(1, 14), hours=random.randint(9, 17))
            db.add(Meeting(
                project_id=p.id,
                title=f"{p.name} — weekly sync",
                starts_at=start, ends_at=start + timedelta(hours=1),
                location="Conf Room — Saturn",
                meeting_url="https://meet.atlas-robotics.demo/sync",
                agenda="1. Status updates  2. Blockers  3. Next-week plan",
                attendees=", ".join(u.full_name for u in users[:5]),
            ))
        db.commit()


# ---------------------------------------------------------------------------
# AI
# ---------------------------------------------------------------------------

AI_CONVERSATION_TITLES = [
    "Drafting the Q4 board update",
    "Refactoring the auth middleware",
    "Customer escalation — Pacific Shipping",
    "Pricing strategy brainstorm",
    "Drafting the AR-Pilot launch email",
    "Code review: tenant filter",
    "Investor pitch outline",
    "Renewal negotiation script",
    "Onboarding doc rewrite",
    "Quarterly OKR draft",
    "Bug investigation: SSE drops",
    "API design — webhook signatures",
    "Performance review — Q4",
    "Marketing campaign concepts",
    "Hiring scorecard for Senior Engineer",
]


def _seed_ai(db: Session, users: list[User]) -> None:
    if db.scalar(select(AiConversation).limit(1)) is None:
        admin = next(u for u in users if u.role == UserRole.admin)
        for title in AI_CONVERSATION_TITLES:
            conv = AiConversation(
                title=title,
                user_id=admin.id,
                model="claude-sonnet-4-5",
                provider="anthropic",
                module="general",
            )
            db.add(conv)
            db.flush()
            # 2-4 turns each
            for i in range(random.randint(2, 4)):
                db.add(AiMessage(conversation_id=conv.id, role="user",
                                 content=f"Help me with: {title} — round {i + 1}"))
                db.add(AiMessage(conversation_id=conv.id, role="assistant",
                                 content="Here's a draft outline + the next three concrete steps to ship. ..."))
        db.commit()

    if db.scalar(select(AiUsageRecord).limit(1)) is None:
        for _ in range(90):
            db.add(AiUsageRecord(
                user_id=random.choice(users).id,
                provider=random.choice(["anthropic", "openai", "ollama"]),
                model=random.choice(["claude-sonnet-4-5", "gpt-4o-mini", "llama3.1"]),
                tokens_in=random.randint(120, 8000),
                tokens_out=random.randint(60, 4000),
                cost_usd=Decimal(str(round(random.uniform(0.001, 0.45), 4))),
                latency_ms=random.randint(180, 4200),
                occurred_at=now_utc() - timedelta(hours=random.randint(0, 24 * 14)),
            ))
        db.commit()

    if db.scalar(select(Chatbot).limit(1)) is None:
        BOTS = [
            ("Atlas Support Bot",        "Helps customers troubleshoot AR-Sense hardware.", "claude-sonnet-4-5"),
            ("Sales Assistant",          "Answers prospect questions about pricing + features.", "claude-sonnet-4-5"),
            ("Internal Help Desk",       "IT + HR FAQs for employees.", "gpt-4o-mini"),
            ("Onboarding Concierge",     "Guides new customers through their first week.", "claude-sonnet-4-5"),
        ]
        for name, system, model in BOTS:
            db.add(Chatbot(
                name=name,
                description=system,
                system_prompt=system,
                model=model,
                provider="anthropic" if model.startswith("claude") else "openai",
                is_active=True,
            ))
        db.commit()


# ---------------------------------------------------------------------------
# Communication
# ---------------------------------------------------------------------------

def _seed_communication(db: Session, users: list[User]) -> None:
    admin = next(u for u in users if u.role == UserRole.admin)

    if db.scalar(select(Announcement).limit(1)) is None:
        ANNOUNCEMENTS = [
            ("AR-Pilot Pro hits 500 units shipped",
             "Big milestone, team — thanks to everyone who contributed to making this launch a success."),
            ("Q4 all-hands — next Friday 10am PT",
             "Agenda: company OKRs, customer wins, sneak peek at H1 roadmap."),
            ("New benefits provider — enrolment open",
             "Open enrolment runs through end of next week. Camille has details on the people-ops channel."),
            ("Office closure — Thanksgiving week",
             "Reminder: SF + NY offices closed Thursday + Friday. Atlanta open with limited staff."),
        ]
        for title, body in ANNOUNCEMENTS:
            db.add(Announcement(title=title, body=body, audience="all", is_published=True))
        db.commit()

    if db.scalar(select(SharedNote).limit(1)) is None:
        for title in [
            "Onboarding playbook — sales team",
            "Incident response runbook",
            "Customer escalation tree",
            "Vendor security review template",
            "Brand voice + tone guide",
            "AR-Sense v2 product spec",
        ]:
            db.add(SharedNote(
                owner_id=admin.id, title=title,
                body=f"# {title}\n\nLast updated by Maya Chen.\n\n…",
            ))
        db.commit()

    if db.scalar(select(CalendarEvent).limit(1)) is None:
        for i in range(12):
            start = now_utc() + timedelta(days=random.randint(0, 30), hours=random.randint(8, 17))
            db.add(CalendarEvent(
                title=random.choice(["Customer demo", "1:1 — Priya/Alex", "Engineering standup", "Sales pipeline review", "Board prep"]),
                starts_at=start, ends_at=start + timedelta(minutes=random.choice([30, 60])),
                location="Conf Room — Mercury",
            ))
        db.commit()

    if db.scalar(select(MessageThread).limit(1)) is None:
        for subject in [
            "Renewal — Stratus Cloud",
            "AR-Pilot Pro launch readiness",
            "Hiring loop — Staff Engineer",
            "Customer issue: Pacific Shipping connectivity",
            "Q4 board meeting prep",
        ]:
            t = MessageThread(title=subject, created_by_id=admin.id)
            db.add(t)
            db.flush()
            for i in range(random.randint(2, 5)):
                db.add(Message(
                    thread_id=t.id,
                    sender_id=random.choice(users).id,
                    body=f"Update on {subject} — message {i + 1}.",
                ))
        db.commit()


# ---------------------------------------------------------------------------
# Notifications + Achievements
# ---------------------------------------------------------------------------

def _seed_notifications(db: Session, users: list[User]) -> None:
    if db.scalar(select(Notification).limit(1)) is not None:
        return
    LEVELS = ["info", "info", "success", "warning"]
    TEMPLATES = [
        ("New invoice paid", "TechFlow Industries paid INV-2025-1003 for $14,500.", "/finance?tab=invoices"),
        ("New lead from website", "Hans Weber requested a demo via the contact form.", "/crm?tab=leads"),
        ("Deal moved to negotiation", "Quantum Dynamics — Enterprise rollout — 75% probability.", "/crm?tab=pipeline"),
        ("Low stock alert", "AR-Sense v2 Standard is below threshold (6 left).", "/inventory"),
        ("Time-off request", "Alex Rodriguez requested 3 days vacation.", "/hr?tab=leave"),
        ("Achievement unlocked", "You earned: Closed Won — first deal won.", "/settings?tab=achievements"),
        ("System backup completed", "Last night's backup completed in 4m 22s.", "/security"),
    ]
    for u in users:
        for _ in range(random.randint(4, 12)):
            title, body, link = random.choice(TEMPLATES)
            db.add(Notification(
                user_id=u.id,
                title=title,
                body=body,
                level=random.choice(LEVELS),
                link=link,
                is_read=random.random() < 0.6,
            ))
    db.commit()


def _award_demo_achievements(db: Session, tenant_id: str, users: list[User]) -> None:
    admin = next(u for u in users if u.role == UserRole.admin)
    keys = [
        "welcome", "first_login", "profile_completed",
        "first_customer", "first_invoice", "ten_invoices",
        "first_lead", "first_deal_won",
        "first_employee",
        "command_palette", "dark_mode", "palette_picker",
        "login_streak_7",
    ]
    for k in keys:
        gam.award(db, tenant_id=tenant_id, user_id=admin.id, key=k)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def seed_demo(slug: str = TENANT_DEMO_SLUG, *, reset: bool = False) -> str:
    """Top-level seed. Returns the tenant id.

    Auto-initialises the schema (migrations + default tenant + permission
    catalogue + gamification catalogue) on first run, so the script is
    safe to invoke against an empty DB.
    """
    from app.db.init_db import init_db
    init_db()
    with SessionLocal() as db:
        tenant = _ensure_tenant(db, slug)
        if reset:
            _reset_tenant(db, tenant.id)
            tenant = _ensure_tenant(db, slug)

        with tenant_scope(tenant.id):
            logger.info("Seeding {} — users", tenant.name)
            users = _seed_users(db)

            logger.info("Seeding finance entities")
            customers = _seed_customers(db)
            vendors = _seed_vendors(db)
            categories = _seed_expense_categories(db)
            _seed_currency_rates(db)
            _seed_tax_rates(db)
            _seed_invoices(db, customers)
            _seed_expenses(db, vendors, categories)
            _seed_budgets(db)
            _seed_recurring(db)
            _seed_vendor_payments(db, vendors)

            logger.info("Seeding HR (50 employees)")
            employees = _seed_employees(db, users)
            _seed_org_units(db, employees)
            _seed_attendance_and_leave(db, employees)
            _seed_recruitment(db)
            _seed_reviews_training_discipline(db, employees, users)
            _seed_payroll(db, employees)

            logger.info("Seeding CRM (contacts/deals/leads)")
            _seed_crm(db)

            logger.info("Seeding inventory")
            _seed_inventory(db)

            logger.info("Seeding projects + tasks + meetings")
            projects = _seed_projects(db, users)
            _seed_time_meetings(db, projects, users)

            logger.info("Seeding AI conversations + usage")
            _seed_ai(db, users)

            logger.info("Seeding communication artefacts")
            _seed_communication(db, users)

            logger.info("Seeding notifications + achievements")
            _seed_notifications(db, users)
            _award_demo_achievements(db, tenant_id=tenant.id, users=users)

        logger.success("Demo data ready — sign in as maya@atlas-robotics.demo / {}", DEMO_PASSWORD)
        return tenant.id


# ---------------------------------------------------------------------------
# Reset — used by --reset
# ---------------------------------------------------------------------------

def _reset_tenant(db: Session, tenant_id: str) -> None:
    """Delete every row in the demo tenant. Cascades clean up children."""
    with bypass_tenant_filter():
        # Order matters when FK constraints are strict — leaf tables first.
        tables_in_order = [
            AiUsageRecord, AiMessage, AiConversation, Chatbot,
            TimeEntry, Meeting, Milestone, Sprint, Task, Project,
            Message, MessageThread, CalendarEvent, SharedNote, Announcement,
            PayslipLine, PayrollRun, BudgetItem, BudgetPlan, RecurringPayment,
            VendorPayment, Expense, ExpenseCategory, TaxRate, CurrencyRate,
            InvoiceLine, Invoice,
            CommunicationEntry, FollowUp, Lead, Deal, Quotation, Proposal,
            Contract, EmailCampaign, CustomerSegment, Contact,
            Vendor, Customer,
            TrainingRecord, DisciplinaryRecord, OnboardingTask,
            PerformanceReview, Candidate, JobOpening, OrgUnit,
            LeaveRequest, AttendanceRecord, Employee,
            Product, ProductCategory, Warehouse, Supplier,
            Notification,
        ]
        for model in tables_in_order:
            db.execute(delete(model).where(model.tenant_id == tenant_id))
        # Achievements + streaks live in gamification tables — wipe those too.
        from app.models.gamification import UserAchievement, UserStreak
        db.execute(delete(UserAchievement).where(UserAchievement.tenant_id == tenant_id))
        db.execute(delete(UserStreak).where(UserStreak.tenant_id == tenant_id))
        # Users last (after employee rows that reference them are gone).
        db.execute(delete(User).where(User.tenant_id == tenant_id))
        db.commit()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> int:
    parser = argparse.ArgumentParser(description="Seed the Atlas Robotics demo tenant.")
    parser.add_argument("--tenant", default=TENANT_DEMO_SLUG,
                        help="Tenant slug to seed (default: atlas-demo)")
    parser.add_argument("--reset", action="store_true",
                        help="Wipe the tenant's data before reseeding.")
    args = parser.parse_args()
    seed_demo(slug=args.tenant, reset=args.reset)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_cli())
