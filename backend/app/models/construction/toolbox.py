"""Toolbox talks — daily safety briefings on site."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class ConstructionToolboxTalk(IdMixin, TenantMixin, TimestampMixin, Base):
    """A toolbox talk — short safety briefing conducted on site.

    ``attachments`` is a JSON array of upload ids (sign-in sheet, slide deck,
    PPE photos). ``attendees_count`` is a plain integer rather than a side
    table — the construction industry typically tracks aggregate headcount
    on the briefing for HSE auditing, not individual attendance.
    """

    __tablename__ = "construction_toolbox_talks"

    construction_project_id: Mapped[str] = mapped_column(
        ForeignKey("construction_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    topic: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    conducted_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True,
    )
    conducted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True,
    )
    attendees_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    key_points: Mapped[str] = mapped_column(Text, default="", nullable=False)
    attachments: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
    )
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
