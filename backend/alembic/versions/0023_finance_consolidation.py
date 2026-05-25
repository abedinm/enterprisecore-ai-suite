"""Phase 10 — multi-entity consolidation tables + per-row entity_id.

Adds three new tables (``subsidiary_entities``, ``intercompany_transactions``,
``fx_adjustments``) and an ``entity_id`` FK column on ``invoices``,
``expenses``, and ``payroll_runs``. For every existing tenant a "Main
Entity" SubsidiaryEntity is auto-provisioned with the tenant's currency
as both functional and reporting currency, and every existing
invoice/expense/payroll row is backfilled to point at it.

Idempotent: each step probes the current schema before acting. Safe to
apply to fresh DBs built via ``Base.metadata.create_all`` (where the
tables and columns already exist from the model metadata) — the backfill
+ main-entity seeding still runs so the data layer stays consistent.
"""
from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0023_finance_consolidation"
down_revision = "0022_jobs"
branch_labels = None
depends_on = None


def _ulid() -> str:
    ts = int(time.time() * 1000)
    rand = secrets.token_hex(10)
    return f"{ts:013x}{rand}"[:26].upper()


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. subsidiary_entities
    # ------------------------------------------------------------------
    if not _has_table("subsidiary_entities"):
        op.create_table(
            "subsidiary_entities",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False, index=True),
            sa.Column("code", sa.String(length=40), nullable=False, index=True),
            sa.Column("country", sa.String(length=2), nullable=False, server_default="US"),
            sa.Column("functional_currency", sa.String(length=3), nullable=False, server_default="USD"),
            sa.Column("reporting_currency", sa.String(length=3), nullable=False, server_default="USD"),
            sa.Column(
                "parent_entity_id",
                sa.String(length=32),
                sa.ForeignKey("subsidiary_entities.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("is_main", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("inception_date", sa.Date()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        )

    # ------------------------------------------------------------------
    # 2. intercompany_transactions
    # ------------------------------------------------------------------
    if not _has_table("intercompany_transactions"):
        op.create_table(
            "intercompany_transactions",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column(
                "from_entity_id",
                sa.String(length=32),
                sa.ForeignKey("subsidiary_entities.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "to_entity_id",
                sa.String(length=32),
                sa.ForeignKey("subsidiary_entities.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("kind", sa.String(length=40), nullable=False, server_default="transfer", index=True),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
            sa.Column("transaction_date", sa.Date(), nullable=False, index=True),
            sa.Column("description", sa.Text()),
            sa.Column("eliminates_on_consolidation", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column(
                "matched_invoice_id",
                sa.String(length=32),
                sa.ForeignKey("invoices.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    # ------------------------------------------------------------------
    # 3. fx_adjustments
    # ------------------------------------------------------------------
    if not _has_table("fx_adjustments"):
        op.create_table(
            "fx_adjustments",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column(
                "entity_id",
                sa.String(length=32),
                sa.ForeignKey("subsidiary_entities.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("account_kind", sa.String(length=20), nullable=False, server_default="ar"),
            sa.Column("original_currency", sa.String(length=3), nullable=False),
            sa.Column("original_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("reporting_currency", sa.String(length=3), nullable=False),
            sa.Column("opening_rate", sa.Numeric(18, 8), nullable=False, server_default="0"),
            sa.Column("closing_rate", sa.Numeric(18, 8), nullable=False, server_default="0"),
            sa.Column("fx_gain_loss", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("period_end", sa.Date(), nullable=False, index=True),
        )

    # ------------------------------------------------------------------
    # 4. Add entity_id to invoices, expenses, payroll_runs
    # ------------------------------------------------------------------
    for table in ("invoices", "expenses", "payroll_runs"):
        if not _has_table(table):
            continue
        if _has_column(table, "entity_id"):
            continue
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("entity_id", sa.String(length=32), nullable=True))
            batch.create_index(f"ix_{table}_entity_id", ["entity_id"])
            batch.create_foreign_key(
                f"fk_{table}_entity_id_subsidiary_entities",
                "subsidiary_entities", ["entity_id"], ["id"], ondelete="SET NULL",
            )

    # ------------------------------------------------------------------
    # 5. Provision a Main Entity per tenant + backfill rows
    # ------------------------------------------------------------------
    tenants = bind.execute(sa.text("SELECT id, currency FROM tenants")).fetchall()
    now = datetime.now(timezone.utc)
    for tenant_id, tenant_currency in tenants:
        currency = (tenant_currency or "USD").upper()
        existing_main = bind.execute(
            sa.text(
                "SELECT id FROM subsidiary_entities "
                "WHERE tenant_id = :tid AND is_main = 1"
            ),
            {"tid": tenant_id},
        ).first()
        if existing_main:
            main_id = existing_main[0]
        else:
            main_id = _ulid()
            bind.execute(
                sa.text(
                    "INSERT INTO subsidiary_entities "
                    "(id, tenant_id, name, code, country, functional_currency, "
                    " reporting_currency, is_main, is_active, created_at, updated_at) "
                    "VALUES (:id, :tid, :name, :code, :country, :fc, :rc, "
                    "        1, 1, :ts, :ts)"
                ),
                {
                    "id": main_id, "tid": tenant_id,
                    "name": "Main Entity", "code": "MAIN",
                    "country": "US", "fc": currency, "rc": currency, "ts": now,
                },
            )

        # Backfill rows that still have NULL entity_id for this tenant.
        for table in ("invoices", "expenses", "payroll_runs"):
            if not _has_column(table, "entity_id"):
                continue
            try:
                bind.execute(
                    sa.text(
                        f"UPDATE {table} SET entity_id = :eid "
                        f"WHERE tenant_id = :tid AND entity_id IS NULL"
                    ),
                    {"eid": main_id, "tid": tenant_id},
                )
            except Exception:
                pass


def downgrade() -> None:
    # Forward-only; lossy downgrade would re-flatten multi-entity data.
    raise NotImplementedError("downgrade not supported")
