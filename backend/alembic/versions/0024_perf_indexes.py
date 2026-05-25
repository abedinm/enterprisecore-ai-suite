"""Phase 11 — composite perf indexes for tenant-scoped status filters.

Adds composite indexes that the auto-filter's ``WHERE tenant_id = ?``
naturally pairs with the hot WHERE clauses we measured during the
performance audit:

* ``(tenant_id, status)`` on ``invoices``, ``jobs`` (jobs already had a
  3-col composite — we leave that alone), ``deals``, ``tasks``,
  ``knowledge_documents``.
* ``(tenant_id, status, created_at)`` on ``invoices`` for the dashboard
  "outstanding / overdue" lists, which order by ``created_at`` after
  filtering by status.
* ``(project_id, status)`` on ``tasks`` for the per-project task list
  (the analytics endpoint's bulk N+1 fix relies on this).
* ``(kb_id, status)`` on ``knowledge_documents`` for the ingest worker
  scan.
* ``(last_message_at)`` on ``webchat_conversations`` for the bot inbox.

Idempotent: each step probes the current schema and uses
``CREATE INDEX IF NOT EXISTS`` semantics via SQLAlchemy's
``Index(..., if_not_exists=...)`` helper where supported, falling back to
manual existence checks otherwise.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "0024_perf_indexes"
down_revision = "0023_finance_consolidation"
branch_labels = None
depends_on = None


# Composite indexes we want, keyed by (table, name) → list of columns.
# The auto-filter prefixes every tenant-scoped SELECT with ``tenant_id``,
# so a leading ``tenant_id`` is the right shape — SQLite + PostgreSQL both
# pick up multi-column index prefixes the way you'd expect.
_INDEXES: list[tuple[str, str, list[str]]] = [
    ("invoices", "ix_invoices_tenant_status", ["tenant_id", "status"]),
    ("invoices", "ix_invoices_tenant_status_created", ["tenant_id", "status", "created_at"]),
    ("deals", "ix_deals_tenant_stage", ["tenant_id", "stage"]),
    ("tasks", "ix_tasks_tenant_status", ["tenant_id", "status"]),
    ("tasks", "ix_tasks_project_status", ["project_id", "status"]),
    ("knowledge_documents", "ix_kdocs_kb_status", ["kb_id", "status"]),
    ("knowledge_documents", "ix_kdocs_tenant_status", ["tenant_id", "status"]),
    ("webchat_conversations", "ix_wcc_last_msg", ["last_message_at"]),
    ("expenses", "ix_expenses_tenant_date", ["tenant_id", "date"]),
]


def _index_exists(bind, table: str, name: str) -> bool:
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    existing = {ix["name"] for ix in insp.get_indexes(table)}
    return name in existing


def _columns_exist(bind, table: str, cols: list[str]) -> bool:
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    present = {c["name"] for c in insp.get_columns(table)}
    return all(c in present for c in cols)


def upgrade() -> None:
    bind = op.get_bind()
    for table, name, cols in _INDEXES:
        if not _columns_exist(bind, table, cols):
            # Table or one of the columns isn't there yet (e.g. running
            # against a partial schema in a downgrade scenario) — skip
            # silently rather than failing the whole migration.
            continue
        if _index_exists(bind, table, name):
            continue
        op.create_index(name, table, cols)


def downgrade() -> None:
    bind = op.get_bind()
    for table, name, _cols in _INDEXES:
        if _index_exists(bind, table, name):
            op.drop_index(name, table_name=table)
