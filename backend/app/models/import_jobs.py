"""Phase 9 — data-migration import jobs.

A two-table model that backs the customer-facing "move your data in from
another SaaS" flow: ``ImportJob`` tracks one upload through the
upload → detect → map → validate → preview → commit → (rollback) lifecycle,
``ImportError`` captures the per-row failures the dry-run / commit produced.

Both tables are tenant-scoped via :class:`TenantMixin` so jobs created in
tenant A are invisible to tenant B (the auto-filter handles WHERE on read
and the before_insert listener fills ``tenant_id`` on write).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class ImportJob(IdMixin, TenantMixin, TimestampMixin, Base):
    """One uploaded file moving through the importer pipeline.

    ``status`` ladder: ``uploaded`` → ``validating`` → ``previewing`` →
    ``importing`` → ``completed`` | ``failed`` | ``rolled_back``.
    ``imported_record_ids`` is the trail of created EC row ids, written as
    a flat ``[(entity_table, pk), ...]`` JSON list so :meth:`rollback` can
    delete the right rows without a separate audit table.
    """

    __tablename__ = "import_jobs"

    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    target_module: Mapped[str] = mapped_column(String(40), nullable=False)
    target_entity: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="uploaded", nullable=False, index=True)
    source_file_path: Mapped[str | None] = mapped_column(String(500))
    column_mapping: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    row_count_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    row_count_imported: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    row_count_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    row_count_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_by_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    options: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    can_rollback: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    imported_record_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class ImportError(IdMixin, TenantMixin, TimestampMixin, Base):
    """Per-row failure recorded during validate or commit.

    ``source_data`` is the raw mapped dict the importer was about to insert
    (helps the customer eyeball "ah, that's the row with a missing email").
    ``error_type``: ``validation`` | ``duplicate`` | ``missing_required_field`` |
    ``unknown``.
    """

    __tablename__ = "import_errors"

    import_job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("import_jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
