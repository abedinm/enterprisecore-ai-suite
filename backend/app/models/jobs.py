"""Background-job observability tables.

RQ keeps its own job state in Redis (queued/started/finished/failed) which
is fine for the worker but useless for the admin UI: it disappears when
the Redis instance is wiped, can't be queried per-tenant, and isn't joined
to any of our domain tables.

These two tables shadow each RQ job with a tenant-scoped DB row so admins
can answer "what jobs have run for *my* tenant in the last week, which
failed, and what was the error message?" without ever touching Redis.

The ``Job`` row is created at ``enqueue()`` time and updated as the worker
moves the job through its lifecycle. Each retry produces a ``JobAttempt``
child row so the admin UI can show the full history without parsing a
single ``last_error`` blob.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON, DateTime, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class Job(IdMixin, TenantMixin, TimestampMixin, Base):
    """One unit of background work.

    ``status`` ladder: ``queued`` → ``running`` → ``completed`` | ``failed``
    | ``cancelled``. ``function_name`` is the dotted import path of the
    callable so the admin UI can group by it ("show me all failed
    webhook deliveries this week").

    ``args_json`` keeps the serializable args/kwargs we enqueued with;
    enough to render a "retry with these args" button. ``result_excerpt``
    is the first 500 chars of whatever the callable returned, str()'d —
    full results live in RQ + are not persisted here.
    """

    __tablename__ = "jobs"

    function_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    args_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False, index=True)
    queue_name: Mapped[str] = mapped_column(String(40), default="default", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_excerpt: Mapped[str | None] = mapped_column(String(500))
    rq_job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    created_by_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    __table_args__ = (
        Index("ix_jobs_tenant_status_created", "tenant_id", "status", "created_at"),
    )


class JobAttempt(IdMixin, TenantMixin, TimestampMixin, Base):
    """One execution attempt of a parent :class:`Job`.

    A fresh row is written every time the worker actually starts the job
    (initial fire + every manual retry), so the admin UI can show the full
    history including transient failures that eventually succeeded.
    """

    __tablename__ = "job_attempts"

    job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
