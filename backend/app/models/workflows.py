"""Workflow + WorkflowRun models — no-code automation engine.

A Workflow listens for one event type (optionally filtered by simple
dotted-key comparison) and executes an ordered list of actions when a
matching event fires. Each execution lands a WorkflowRun row recording
the per-action outcome so a tenant admin can audit *why* a particular
follow-up email or Slack message did or didn't go out.

Caps applied at the endpoint layer (see ``app/api/v1/endpoints/workflows.py``):

* Max 100 active workflows per tenant.
* Max 10 actions per workflow.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class Workflow(IdMixin, TenantMixin, TimestampMixin, Base):
    """A single 'if-this-then-that' rule.

    ``trigger_event_type`` is an :data:`app.services.event_bus.EVENT_TYPES`
    key or a wildcard pattern (``crm.*``, ``*.created``). ``trigger_filter``
    is a flat dict of ``{"dotted.payload.key": value_or_op_string}``
    pairs — see :func:`app.services.workflow_engine._filter_matches`.

    ``actions`` is a JSON list of ``{type, config}`` records executed in
    order. Templates inside the ``config`` strings are rendered with
    Jinja2 against the event payload.
    """

    __tablename__ = "workflows"

    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    trigger_event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    trigger_filter: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    actions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_by_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    runs_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failures_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class WorkflowRun(IdMixin, TenantMixin, TimestampMixin, Base):
    """One execution of a Workflow against a specific Event.

    ``status`` is ``success`` when every action returned ok, ``partial``
    when at least one action failed but the workflow continued, or
    ``failure`` when no action succeeded. ``action_results`` mirrors the
    workflow's ``actions`` list — one entry per executed action with its
    own ``{ok, error, detail}`` payload.
    """

    __tablename__ = "workflow_runs"

    workflow_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workflows.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    event_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="success", index=True)
    action_results: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
