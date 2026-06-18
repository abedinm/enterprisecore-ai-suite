"""Pydantic schemas for finance endpoints."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import ORMModel
from app.schemas.validators import (
    non_negative_money,
    positive_quantity,
    tax_rate_fraction,
    validate_currency,
    validate_email_opt,
    validate_phone_opt,
)


# ---- Customers / Vendors -------------------------------------------------
class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    email: str | None = None
    phone: str | None = None
    billing_address: str | None = Field(default=None, max_length=2000)
    currency: str = "USD"

    _v_email = field_validator("email")(staticmethod(validate_email_opt))
    _v_phone = field_validator("phone")(staticmethod(validate_phone_opt))
    _v_ccy = field_validator("currency")(staticmethod(validate_currency))

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Customer name can't be empty.")
        return v.strip()


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
    payment_terms: str | None = Field(default=None, max_length=120)

    _v_email = field_validator("email")(staticmethod(validate_email_opt))
    _v_phone = field_validator("phone")(staticmethod(validate_phone_opt))

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Vendor name can't be empty.")
        return v.strip()


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

    @field_validator("description")
    @classmethod
    def _desc_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Line description can't be empty.")
        return v.strip()

    _v_qty = field_validator("quantity")(staticmethod(positive_quantity))
    _v_price = field_validator("unit_price")(
        staticmethod(lambda v: non_negative_money(v, "unit price"))
    )
    _v_tax = field_validator("tax_rate")(staticmethod(tax_rate_fraction))


class InvoiceLineOut(ORMModel):
    id: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    line_total: Decimal


class InvoiceIn(BaseModel):
    customer_id: str | None = None
    invoice_number: str | None = Field(default=None, max_length=60)
    issue_date: date
    due_date: date
    currency: str = "USD"
    notes: str | None = Field(default=None, max_length=4000)
    discount_total: Decimal = Decimal("0")
    lines: list[InvoiceLineIn] = Field(default_factory=list, max_length=200)

    _v_ccy = field_validator("currency")(staticmethod(validate_currency))
    _v_disc = field_validator("discount_total")(
        staticmethod(lambda v: non_negative_money(v, "discount"))
    )

    @model_validator(mode="after")
    def _dates_in_order(self):
        if self.due_date < self.issue_date:
            raise ValueError("Due date can't be earlier than the issue date.")
        return self


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


_INVOICE_STATUSES = {"draft", "sent", "paid", "overdue", "void"}


class InvoiceStatusUpdate(BaseModel):
    status: str  # draft|sent|paid|overdue|void

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        s = (v or "").strip().lower()
        if s not in _INVOICE_STATUSES:
            raise ValueError(
                f"Invalid status '{v}'. Must be one of: {', '.join(sorted(_INVOICE_STATUSES))}."
            )
        return s


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
