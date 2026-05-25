"""Background-job observability tables.

Two new tables — ``jobs`` and ``job_attempts`` — that shadow each RQ
background job with a tenant-scoped DB row so admins can answer
"what ran for *my* tenant in the last week, which failed, and what was
the error message?" without ever touching Redis.

Idempotent — if the tables already exist (fresh DB built from
metadata.create_all in tests), this migration is a no-op.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0022_jobs"
down_revision = "0021_fts5_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing = set(insp.get_table_names())

    if "jobs" not in existing:
        op.create_table(
            "jobs",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("function_name", sa.String(length=200), nullable=False, index=True),
            sa.Column("args_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, index=True),
            sa.Column("queue_name", sa.String(length=40), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("last_error", sa.Text()),
            sa.Column("scheduled_at", sa.DateTime(timezone=True)),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
            sa.Column("result_excerpt", sa.String(length=500)),
            sa.Column("rq_job_id", sa.String(length=64), index=True),
            sa.Column("created_by_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="SET NULL"), index=True),
        )
        op.create_index(
            "ix_jobs_tenant_status_created", "jobs",
            ["tenant_id", "status", "created_at"],
        )

    if "job_attempts" not in existing:
        op.create_table(
            "job_attempts",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("job_id", sa.String(length=32), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("attempt_number", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True)),
            sa.Column("duration_ms", sa.Integer()),
            sa.Column("error_message", sa.Text()),
        )


def downgrade() -> None:
    # Forward-only.
    raise NotImplementedError("downgrade not supported")
