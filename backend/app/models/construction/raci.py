"""RACI matrix — Responsible / Accountable / Consulted / Informed per activity."""
from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class ConstructionRaciEntry(IdMixin, TenantMixin, TimestampMixin, Base):
    """One row of the RACI matrix.

    ``consulted`` and ``informed`` are JSON arrays of user ids because a
    single activity can have many people in each role. The unique
    Responsible/Accountable pair (one each per row) is enforced by column
    typing.
    """

    __tablename__ = "construction_raci_entries"

    construction_project_id: Mapped[str] = mapped_column(
        ForeignKey("construction_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    activity: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    responsible_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True,
    )
    accountable_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True,
    )
    consulted: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    informed: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
