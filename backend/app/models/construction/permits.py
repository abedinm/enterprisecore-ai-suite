"""Construction permits — building, planning, environmental, etc."""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class ConstructionPermit(IdMixin, TenantMixin, TimestampMixin, Base):
    """One permit on a project (building, planning, environmental, etc.).

    ``document_id`` is a soft pointer to the Documents module — nullable
    because not every permit has a digital attachment yet. We don't enforce
    the FK to ``documents`` here so the Documents table staying out of the
    construction module's blast radius keeps cascades simple.
    """

    __tablename__ = "construction_permits"

    construction_project_id: Mapped[str] = mapped_column(
        ForeignKey("construction_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    permit_type: Mapped[str] = mapped_column(
        String(120), default="", nullable=False, index=True,
    )
    issuing_authority: Mapped[str] = mapped_column(
        String(200), default="", nullable=False,
    )
    application_date: Mapped[date | None] = mapped_column(Date)
    approval_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date, index=True)
    # draft | submitted | under_review | approved | rejected | expired
    status: Mapped[str] = mapped_column(
        String(16), default="draft", nullable=False, index=True,
    )
    reference_number: Mapped[str] = mapped_column(
        String(120), default="", nullable=False, index=True,
    )
    conditions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    document_id: Mapped[str | None] = mapped_column(String(64))
