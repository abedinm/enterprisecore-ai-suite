"""Site instructions (SIs) — directives issued by the PM to the contractor."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class ConstructionSiteInstruction(IdMixin, TenantMixin, TimestampMixin, Base):
    """A numbered site instruction issued to the contractor.

    ``number`` is auto-generated server-side as ``SI-001``, ``SI-002`` ...
    scoped per construction project. The uniqueness constraint protects the
    invariant when two writers race for the same number.
    """

    __tablename__ = "construction_site_instructions"

    construction_project_id: Mapped[str] = mapped_column(
        ForeignKey("construction_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    issued_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True,
    )
    issued_to: Mapped[str] = mapped_column(
        String(200), default="", nullable=False,
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_required_by: Mapped[date | None] = mapped_column(Date)
    # issued | acknowledged | in_progress | completed | disputed
    status: Mapped[str] = mapped_column(
        String(16), default="issued", nullable=False, index=True,
    )
    response: Mapped[str | None] = mapped_column(Text)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "construction_project_id", "number",
            name="uq_construction_si_project_number",
        ),
    )
