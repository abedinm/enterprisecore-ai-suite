"""Site progress reports — one row per submission, usually daily."""
from __future__ import annotations

from datetime import date

from sqlalchemy import JSON, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class ConstructionProgressReport(IdMixin, TenantMixin, TimestampMixin, Base):
    """A daily/weekly progress report from site.

    ``photos`` is a JSON array of upload ids so the report can reference any
    number of images without a side table. ``weather_conditions`` is free
    text on purpose — different climates need different vocabularies.
    """

    __tablename__ = "construction_progress_reports"

    construction_project_id: Mapped[str] = mapped_column(
        ForeignKey("construction_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    overall_progress_percent: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    narrative: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reported_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True,
    )
    photos: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    weather_conditions: Mapped[str] = mapped_column(
        String(120), default="", nullable=False,
    )
    workforce_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
