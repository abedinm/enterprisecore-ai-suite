from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class Project(IdMixin, TenantMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(180), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    budget: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    color: Mapped[str] = mapped_column(String(16), default="#4F46E5")
    progress: Mapped[int] = mapped_column(Integer, default=0)


class Task(IdMixin, TenantMixin, TimestampMixin, Base):
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    sprint_id: Mapped[str | None] = mapped_column(ForeignKey("sprints.id", ondelete="SET NULL"), index=True)
    assignee_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(180), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="todo", index=True)
    priority: Mapped[str] = mapped_column(String(30), default="medium")
    due_date: Mapped[date | None] = mapped_column(Date)
    start_date: Mapped[date | None] = mapped_column(Date)
    estimated_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=0)
    actual_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=0)
    story_points: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[str] = mapped_column(String(255), default="")


class Sprint(IdMixin, TenantMixin, TimestampMixin, Base):
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    goal: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="planned")
    capacity_points: Mapped[int] = mapped_column(Integer, default=0)


class Milestone(IdMixin, TenantMixin, TimestampMixin, Base):
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), default="open")
    progress: Mapped[int] = mapped_column(Integer, default=0)


class TimeEntry(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "time_entries"

    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    minutes: Mapped[int] = mapped_column(default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_billable: Mapped[bool] = mapped_column(Boolean, default=True)


class Meeting(IdMixin, TenantMixin, TimestampMixin, Base):
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(180))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(255))
    meeting_url: Mapped[str | None] = mapped_column(String(500))
    agenda: Mapped[str] = mapped_column(Text, default="")
    attendees: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="scheduled")


class MeetingMinute(IdMixin, TenantMixin, TimestampMixin, Base):
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text, default="")
    decisions: Mapped[str] = mapped_column(Text, default="")
    action_items: Mapped[str] = mapped_column(Text, default="")


class Resource(IdMixin, TenantMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(180), index=True)
    role: Mapped[str] = mapped_column(String(80), default="")
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    capacity_hours_per_week: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=40)
    skills: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ResourceAllocation(IdMixin, TenantMixin, TimestampMixin, Base):
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    allocation_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=100)
    notes: Mapped[str] = mapped_column(Text, default="")


class TaskDependency(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "task_dependencies"

    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    depends_on_task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    dep_type: Mapped[str] = mapped_column(String(20), default="finish_to_start")
