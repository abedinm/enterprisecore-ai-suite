"""Pydantic schemas for finance endpoints."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ORMModel


# ---- Customers / Vendors -------------------------------------------------
class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    email: str | None = None
    phone: str | None = None
    billing_address: str | None = None
    currency: str = "USD"


class CustomerOut(ORMModel):
    id: str
    name: str
    email: str | None = None
    phone: str | None = None
    billing_address: str | None = None
    currency: str


class VendorIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    email: str | None = None
    phone: str | None = None
    payment_terms: str | None = None


class VendorOut(ORMModel):
    id: str
    name: str
    email: str | None = None
    phone: str | None = None
    payment_terms: str | None = None


# ---- Invoices ------------------------------------------------------------
class InvoiceLineIn(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Decimal("1")
    unit_price: Decimal = Decimal("0")
    tax_rate: Decimal = Decimal("0")  # e.g. 0.20 for 20%


class InvoiceLineOut(ORMModel):
    id: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    line_total: Decimal


class InvoiceIn(BaseModel):
    customer_id: str | None = None
    invoice_number: str | None = None  # auto-generated when missing
    issue_date: date
    due_date: date
    currency: str = "USD"
    notes: str | None = None
    discount_total: Decimal = Decimal("0")
    lines: list[InvoiceLineIn] = []


class InvoiceOut(ORMModel):
    id: str
    invoice_number: str
    customer_id: str | None
    issue_date: date
    due_date: date
    status: str
    currency: str
    subtotal: Decimal
    tax_total: Decimal
    discount_total: Decimal
    total: Decimal
    notes: str | None
    lines: list[InvoiceLineOut] = []
    created_at: datetime


class InvoiceStatusUpdate(BaseModel):
    status: str  # draft|sent|paid|overdue|void


# ---- Expenses ------------------------------------------------------------
class ExpenseIn(BaseModel):
    category_id: str | None = None
    vendor_id: str | None = None
    date: date
    amount: Decimal
    currency: str = "USD"
    description: str = ""
    receipt_path: str | None = None


class ExpenseOut(ORMModel):
    id: str
    category_id: str | None
    vendor_id: str | None
    date: date
    amount: Decimal
    currency: str
    description: str
    receipt_path: str | None
    created_at: datetime


class ExpenseCategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ExpenseCategoryOut(ORMModel):
    id: str
    name: str


# ---- Payroll -------------------------------------------------------------
class PayrollLineIn(BaseModel):
    employee_id: str | None = None
    label: str
    amount: Decimal
    kind: str = "earning"  # earning|deduction|tax|bonus


class PayrollRunIn(BaseModel):
    period_start: date
    period_end: date
    lines: list[PayrollLineIn] = []


class PayslipLineOut(ORMModel):
    id: str
    employee_id: str | None
    label: str
    amount: Decimal
    kind: str


class PayrollRunOut(ORMModel):
    id: str
    period_start: date
    period_end: date
    status: str
    gross_total: Decimal
    deduction_total: Decimal
    net_total: Decimal


class PayrollEstimateIn(BaseModel):
    gross_salary: Decimal
    pay_frequency: str = "monthly"  # weekly|biweekly|monthly|annual
    tax_rate: Decimal = Decimal("0.22")  # combined rate
    deductions: Decimal = Decimal("0")
    bonuses: Decimal = Decimal("0")


class PayrollEstimateOut(BaseModel):
    gross: Decimal
    tax: Decimal
    deductions: Decimal
    bonuses: Decimal
    net: Decimal
    frequency: str = "monthly"


# ---- Budgets / Tax / Recurring ------------------------------------------
class BudgetItemIn(BaseModel):
    category: str
    planned_amount: Decimal = Decimal("0")
    actual_amount: Decimal = Decimal("0")


class BudgetPlanIn(BaseModel):
    name: str
    fiscal_year: int
    currency: str = "USD"
    items: list[BudgetItemIn] = []


class BudgetItemOut(ORMModel):
    id: str
    category: str
    planned_amount: Decimal
    actual_amount: Decimal


class BudgetPlanOut(ORMModel):
    id: str
    name: str
    fiscal_year: int
    currency: str
    items: list[BudgetItemOut] = []


class BudgetActualRow(BaseModel):
    id: str
    category: str
    planned: Decimal
    actual: Decimal
    variance: Decimal
    utilization: Decimal


class BudgetAnalyticsOut(BaseModel):
    plan_id: str
    name: str
    fiscal_year: int
    currency: str
    rows: list[BudgetActualRow]
    totals: dict[str, Decimal]


class TaxRateIn(BaseModel):
    jurisdiction: str
    name: str
    rate: Decimal


class TaxRateOut(ORMModel):
    id: str
    jurisdiction: str
    name: str
    rate: Decimal


class TaxBracketRow(BaseModel):
    from_: Decimal = Field(alias="from")
    to: Decimal
    rate: Decimal
    taxable: Decimal
    tax: Decimal
    model_config = ConfigDict(populate_by_name=True)


class TaxEstimateIn(BaseModel):
    income: Decimal
    deductions: Decimal = Decimal("0")
    brackets: list[tuple[Decimal, Decimal]] = []  # [(threshold, rate)]


class TaxEstimateOut(BaseModel):
    taxable_income: Decimal
    estimated_tax: Decimal
    effective_rate: Decimal
    breakdown: list[dict[str, Any]] = []


class RecurringPaymentIn(BaseModel):
    title: str
    amount: Decimal
    currency: str = "USD"
    cadence: str = "monthly"
    next_due_date: date | None = None


class RecurringPaymentOut(ORMModel):
    id: str
    title: str
    amount: Decimal
    currency: str
    cadence: str
    next_due_date: date | None


# ---- Vendor Payments -----------------------------------------------------
class VendorPaymentIn(BaseModel):
    vendor_id: str | None = None
    payment_date: date
    amount: Decimal
    status: str = "scheduled"
    currency: str = "USD"
    reference: str | None = None
    notes: str | None = None


class VendorPaymentOut(BaseModel):
    id: str
    vendor_id: str | None
    payment_date: date
    amount: Decimal
    status: str
    currency: str | None = None
    reference: str | None = None
    notes: str | None = None


# ---- Currency ------------------------------------------------------------
class CurrencyRateIn(BaseModel):
    base_currency: Annotated[str, Field(min_length=3, max_length=3)]
    quote_currency: Annotated[str, Field(min_length=3, max_length=3)]
    rate: Decimal
    effective_date: date


class CurrencyRateOut(ORMModel):
    id: str
    base_currency: str
    quote_currency: str
    rate: Decimal
    effective_date: date


class ConversionIn(BaseModel):
    amount: Decimal
    from_currency: Annotated[str, Field(min_length=3, max_length=3)]
    to_currency: Annotated[str, Field(min_length=3, max_length=3)]
    as_of: date | None = None


class ConversionOut(BaseModel):
    amount: Decimal
    converted: Decimal
    rate: Decimal
    from_currency: str
    to_currency: str
    as_of: date


class MultiCurrencyEntry(BaseModel):
    currency: str
    invoiced: Decimal
    paid: Decimal
    outstanding: Decimal
    expenses: Decimal
    net: Decimal


class MultiCurrencyOut(BaseModel):
    as_of: date
    currencies: list[MultiCurrencyEntry]


# ---- Reports -------------------------------------------------------------
class PnLOut(BaseModel):
    period_start: date
    period_end: date
    revenue: Decimal
    cogs: Decimal = Decimal("0")
    gross_profit: Decimal
    operating_expenses: Decimal
    net_income: Decimal
    by_category: dict[str, Decimal] = {}


class BalanceSheetOut(BaseModel):
    as_of: date
    assets: dict[str, Decimal]
    liabilities: dict[str, Decimal]
    equity: dict[str, Decimal]
    totals: dict[str, Decimal]


class CashFlowEntryOut(BaseModel):
    period: str  # YYYY-MM
    inflow: Decimal
    outflow: Decimal
    net: Decimal


class CashFlowOut(BaseModel):
    period_start: date
    period_end: date
    entries: list[CashFlowEntryOut]
    totals: dict[str, Decimal]


class ForecastPoint(BaseModel):
    period: str
    revenue_forecast: Decimal
    expense_forecast: Decimal
    net_forecast: Decimal


class ForecastOut(BaseModel):
    method: str
    months_ahead: int
    points: list[ForecastPoint]
    history: list[CashFlowEntryOut] = []
    confidence: Decimal


class DashboardKpis(BaseModel):
    ytd_revenue: Decimal
    ytd_expenses: Decimal
    ytd_net: Decimal
    outstanding: Decimal
    active_customers: int
    active_vendors: int
    open_invoices: int
    overdue_invoices: int
    recurring_count: int


class DashboardOut(BaseModel):
    generated_at: datetime
    period_start: date
    period_end: date
    kpis: DashboardKpis
    revenue_by_month: list[dict[str, Any]] = []
    expenses_by_category: dict[str, Decimal] = {}
    top_customers: list[dict[str, Any]] = []
    top_vendors: list[dict[str, Any]] = []
    upcoming_recurring: list[dict[str, Any]] = []


class AuditTrailItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    action: str
    entity_type: str
    entity_id: str | None
    actor_id: str | None
    detail: str
    created_at: datetime
