"""WBS-style schedule tasks + Gantt-style dependencies."""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class ConstructionScheduleTask(IdMixin, TenantMixin, TimestampMixin, Base):
    """One task in the construction schedule (work breakdown structure).

    ``parent_task_id`` is a self-FK so the WBS can be arbitrarily deep —
    summary tasks roll up their children in the UI. ``progress_percent`` is
    stored separately from ``status`` so a "delayed" task can still report
    real partial progress.
    """

    __tablename__ = "construction_schedule_tasks"

    construction_project_id: Mapped[str] = mapped_column(
        ForeignKey("construction_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    parent_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("construction_schedule_tasks.id", ondelete="SET NULL"),
        index=True,
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    duration_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assigned_to_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True,
    )
    progress_percent: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    # not_started | in_progress | completed | delayed
    status: Mapped[str] = mapped_column(
        String(16), default="not_started", nullable=False, index=True,
    )


class ConstructionScheduleDependency(IdMixin, TenantMixin, TimestampMixin, Base):
    """Edge between two schedule tasks; used by the Gantt renderer.

    Default ``dependency_type`` is ``finish_start`` — the predecessor must
    finish before the successor starts (the most common case). ``lag_days``
    is signed so a negative value expresses "lead time" (start the successor
    before the predecessor finishes).
    """

    __tablename__ = "construction_schedule_dependencies"

    predecessor_id: Mapped[str] = mapped_column(
        ForeignKey("construction_schedule_tasks.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    successor_id: Mapped[str] = mapped_column(
        ForeignKey("construction_schedule_tasks.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # finish_start | start_start | finish_finish | start_finish
    dependency_type: Mapped[str] = mapped_column(
        String(16), default="finish_start", nullable=False,
    )
    lag_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
