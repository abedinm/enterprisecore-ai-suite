"""Construction contracts — FIDIC / NEC / JCT / AIA / custom."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class ConstructionContract(IdMixin, TenantMixin, TimestampMixin, Base):
    """A signed contract on the project (head contract, subcontract, etc.).

    ``contract_type`` is validated at the schema layer to one of the standard
    industry forms (FIDIC, NEC, JCT, AIA) plus ``custom`` for everything else;
    storing it as free-text VARCHAR keeps the table portable across SQL
    dialects.
    """

    __tablename__ = "construction_contracts"

    construction_project_id: Mapped[str] = mapped_column(
        ForeignKey("construction_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    contract_number: Mapped[str] = mapped_column(
        String(120), default="", nullable=False, index=True,
    )
    # FIDIC | NEC | JCT | AIA | custom
    contract_type: Mapped[str] = mapped_column(
        String(16), default="custom", nullable=False,
    )
    counterparty: Mapped[str] = mapped_column(
        String(200), default="", nullable=False,
    )
    value: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="USD", nullable=False,
    )
    signed_date: Mapped[date | None] = mapped_column(Date)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    retention_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0"), nullable=False,
    )
    defects_liability_period_days: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    payment_terms: Mapped[str] = mapped_column(
        Text, default="", nullable=False,
    )
    document_id: Mapped[str | None] = mapped_column(String(64))
