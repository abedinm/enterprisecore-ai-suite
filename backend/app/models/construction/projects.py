"""Construction-specific project record.

Optionally links to the generic :class:`Project` in ``app/models/projects.py``
via ``generic_project_id`` — that lets a customer who already created a
project under the always-on Projects module attach construction-specific
metadata (contract value, location, project_type) without duplicating the
record. ``generic_project_id`` is nullable so a brand-new construction
project can be created without first needing a generic project shell.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class ConstructionProject(IdMixin, TenantMixin, TimestampMixin, Base):
    """One construction project (a job, build, or contract).

    ``project_type`` and ``status`` are validated at the schema layer rather
    than via DB CHECK constraints so adding a new bucket (eg. "renovation") is
    a one-line schema change without a migration.
    """

    __tablename__ = "construction_projects"

    generic_project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    client_name: Mapped[str] = mapped_column(
        String(200), default="", nullable=False,
    )
    location: Mapped[str] = mapped_column(
        String(300), default="", nullable=False,
    )
    # residential | commercial | industrial | infrastructure
    project_type: Mapped[str] = mapped_column(
        String(24), nullable=False, index=True,
    )
    contract_value: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="USD", nullable=False,
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    expected_end_date: Mapped[date | None] = mapped_column(Date)
    actual_end_date: Mapped[date | None] = mapped_column(Date)
    # planning | active | on_hold | completed | cancelled
    status: Mapped[str] = mapped_column(
        String(24), default="planning", nullable=False, index=True,
    )
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
