"""Multi-entity / multinational consolidation models.

A ``SubsidiaryEntity`` is a legal entity (a sub-org) belonging to a tenant.
The "main" entity is auto-provisioned per tenant by the 0023 migration and
every existing Invoice/Expense/Payroll row is backfilled to point at it.
``IntercompanyTransaction`` records loans / management fees / cost
allocations between two entities of the same tenant; flagged rows wash
out at consolidation. ``FxAdjustment`` records gain/loss recognised when
foreign-currency monetary balances are remeasured at period close.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class SubsidiaryEntity(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "subsidiary_entities"

    name: Mapped[str] = mapped_column(String(200), index=True)
    code: Mapped[str] = mapped_column(String(40), index=True)  # "MAIN", "UK-LTD"
    country: Mapped[str] = mapped_column(String(2), default="US")  # ISO 3166-1 alpha-2
    functional_currency: Mapped[str] = mapped_column(String(3), default="USD")
    reporting_currency: Mapped[str] = mapped_column(String(3), default="USD")
    parent_entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("subsidiary_entities.id", ondelete="SET NULL")
    )
    is_main: Mapped[bool] = mapped_column(Boolean, default=False)
    inception_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class IntercompanyTransaction(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "intercompany_transactions"

    from_entity_id: Mapped[str] = mapped_column(
        ForeignKey("subsidiary_entities.id", ondelete="CASCADE"), index=True
    )
    to_entity_id: Mapped[str] = mapped_column(
        ForeignKey("subsidiary_entities.id", ondelete="CASCADE"), index=True
    )
    # "loan" | "management_fee" | "cost_allocation" | "transfer"
    kind: Mapped[str] = mapped_column(String(40), default="transfer", index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    eliminates_on_consolidation: Mapped[bool] = mapped_column(Boolean, default=True)
    matched_invoice_id: Mapped[str | None] = mapped_column(
        ForeignKey("invoices.id", ondelete="SET NULL")
    )


class FxAdjustment(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "fx_adjustments"

    entity_id: Mapped[str] = mapped_column(
        ForeignKey("subsidiary_entities.id", ondelete="CASCADE"), index=True
    )
    # "ar" | "ap" | "loan" | "cash"
    account_kind: Mapped[str] = mapped_column(String(20), default="ar")
    original_currency: Mapped[str] = mapped_column(String(3))
    original_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    reporting_currency: Mapped[str] = mapped_column(String(3))
    opening_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=0)
    closing_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=0)
    # signed; positive = gain, negative = loss (in reporting_currency)
    fx_gain_loss: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    period_end: Mapped[date] = mapped_column(Date, index=True)
