from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class Customer(IdMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(180), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(80))
    billing_address: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(3), default="USD")


class Vendor(IdMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(180), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(80))
    payment_terms: Mapped[str | None] = mapped_column(String(120))


class Invoice(IdMixin, TimestampMixin, Base):
    invoice_number: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"))
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    lines: Mapped[list[InvoiceLine]] = relationship(back_populates="invoice", cascade="all, delete-orphan")


class InvoiceLine(IdMixin, TimestampMixin, Base):
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class ExpenseCategory(IdMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(120), unique=True)


class Expense(IdMixin, TimestampMixin, Base):
    category_id: Mapped[str | None] = mapped_column(ForeignKey("expense_categorys.id", ondelete="SET NULL"))
    vendor_id: Mapped[str | None] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"))
    date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    description: Mapped[str] = mapped_column(Text, default="")
    receipt_path: Mapped[str | None] = mapped_column(String(500))


class PayrollRun(IdMixin, TimestampMixin, Base):
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    gross_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    deduction_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    net_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)


class PayslipLine(IdMixin, TimestampMixin, Base):
    payroll_run_id: Mapped[str] = mapped_column(ForeignKey("payroll_runs.id", ondelete="CASCADE"))
    employee_id: Mapped[str | None] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(160))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    kind: Mapped[str] = mapped_column(String(30), default="earning")


class BudgetPlan(IdMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(160), index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, index=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")


class BudgetItem(IdMixin, TimestampMixin, Base):
    budget_plan_id: Mapped[str] = mapped_column(ForeignKey("budget_plans.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(120))
    planned_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)


class TaxRate(IdMixin, TimestampMixin, Base):
    jurisdiction: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(120))
    rate: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=0)


class RecurringPayment(IdMixin, TimestampMixin, Base):
    title: Mapped[str] = mapped_column(String(160))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    cadence: Mapped[str] = mapped_column(String(40), default="monthly")
    next_due_date: Mapped[date | None] = mapped_column(Date)


class VendorPayment(IdMixin, TimestampMixin, Base):
    vendor_id: Mapped[str | None] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"))
    payment_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(30), default="scheduled")


class JournalEntry(IdMixin, TimestampMixin, Base):
    entry_date: Mapped[date] = mapped_column(Date)
    memo: Mapped[str] = mapped_column(Text, default="")
    lines: Mapped[list[JournalLine]] = relationship(back_populates="entry", cascade="all, delete-orphan")


class JournalLine(IdMixin, TimestampMixin, Base):
    journal_entry_id: Mapped[str] = mapped_column(ForeignKey("journal_entrys.id", ondelete="CASCADE"))
    account: Mapped[str] = mapped_column(String(160))
    debit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    credit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    entry: Mapped[JournalEntry] = relationship(back_populates="lines")


class CurrencyRate(IdMixin, TimestampMixin, Base):
    base_currency: Mapped[str] = mapped_column(String(3), index=True)
    quote_currency: Mapped[str] = mapped_column(String(3), index=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    effective_date: Mapped[date] = mapped_column(Date, index=True)
