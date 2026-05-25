"""Multi-tenancy — Tenant + TenantInvite tables, tenant_id on every business table.

Adds the foundational tenants table and backfills every pre-existing row in
the database to a single "Default Tenant" so the upgrade is non-destructive
on already-deployed installs. After this migration every business table has
``tenant_id NOT NULL`` (FK to ``tenants.id``, ``ondelete=CASCADE``), and the
single-tenant data layout is preserved as "tenant slug = default".

Idempotent: every step probes the current schema before acting. Safe to
re-run on a partially-applied install and safe to apply to fresh DBs built
via ``Base.metadata.create_all`` (which already creates the new tables and
columns from the tenant-aware SQLAlchemy metadata).

Revision ID: 0013_multitenant
Revises: 0012_construction
Create Date: 2026-05-23
"""
from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision: str = "0013_multitenant"
down_revision: str | None = "0012_construction"
branch_labels: str | None = None
depends_on: str | None = None


# Every table that takes tenant_id. Order DOES NOT matter for column adds
# since we batch-alter independently and the FK target (tenants) is created
# first. Listed alphabetically by module for readability.
TENANT_SCOPED_TABLES = [
    # Foundation
    "users", "refresh_tokens", "settings", "audit_logs",
    "notifications", "search_indices", "search_histories",
    # Finance
    "customers", "vendors", "invoices", "invoice_lines",
    "expense_categories", "expenses", "payroll_runs", "payslip_lines",
    "budget_plans", "budget_items", "tax_rates", "recurring_payments",
    "vendor_payments", "journal_entries", "journal_lines", "currency_rates",
    # HR
    "employees", "attendance_records", "leave_requests",
    "performance_reviews", "job_openings", "candidates", "onboarding_tasks",
    "org_units", "training_records", "disciplinary_records",
    # CRM
    "contacts", "leads", "deals", "follow_ups", "communication_entries",
    "contracts", "proposals", "quotations", "email_campaigns",
    "customer_segments",
    # Projects
    "projects", "tasks", "sprints", "milestones", "time_entries",
    "meetings", "meeting_minutes", "resources", "resource_allocations",
    "task_dependencies",
    # Inventory
    "suppliers", "warehouses", "warehouse_zones", "product_categories",
    "products", "stock_movements", "purchase_orders", "purchase_order_lines",
    "shipments", "shipment_events", "return_requests", "stock_alerts",
    # Documents
    "documents", "document_versions", "document_tags", "document_shares",
    "e_signatures", "document_templates",
    # Communication
    "message_threads", "messages", "announcements", "calendar_events",
    "shared_notes", "polls", "poll_options", "poll_votes", "feedbacks",
    "wiki_pages",
    # Security
    "password_vault_entries", "backup_schedules", "login_attempts",
    "compliance_checks",
    # Coding
    "code_projects", "code_snippets", "api_requests", "git_repos",
    "regex_library_entries", "database_connections",
    # AI
    "ai_conversations", "ai_messages", "ai_usage_records", "chatbots",
    "chatbot_messages",
    # Knowledge
    "knowledge_bases", "knowledge_documents", "knowledge_chunks",
    "knowledge_queries",
    # Webchat
    "webchat_bots", "webchat_conversations", "webchat_messages",
    # Marketing
    "marketing_settings", "marketing_nav_items", "marketing_sections",
    "marketing_projects", "marketing_posts", "marketing_services",
    "marketing_testimonials", "marketing_faqs", "marketing_team",
    "marketing_social_links", "marketing_uploads",
    # Academic
    "academic_advising_sessions", "academic_assignments",
    "academic_assignment_submissions", "academic_attendance_records",
    "academic_classes", "academic_class_enrollments", "academic_exams",
    "academic_group_projects", "academic_group_project_assignments",
    "academic_lab_reports", "academic_lms_resources", "academic_rooms",
    "academic_scholarships", "academic_semesters",
    "academic_student_budgets", "academic_student_finance_records",
    "academic_study_group_matches", "academic_study_notes",
    "academic_study_profiles", "academic_study_quiz_attempts",
    "academic_timetable_slots",
    # Construction
    "construction_contracts", "construction_eot_requests",
    "construction_insurances", "construction_milestones",
    "construction_permits", "construction_progress_reports",
    "construction_projects", "construction_raci_entries",
    "construction_risks", "construction_schedule_dependencies",
    "construction_schedule_tasks", "construction_site_instructions",
    "construction_toolbox_talks", "construction_variations",
]


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return any(c["name"] == column for c in _inspector().get_columns(table))


def _ulid() -> str:
    """Match the ULID strategy used by IdMixin so the seeded tenant id looks
    like every other id in the database."""
    try:
        from ulid import ULID
        return str(ULID())
    except Exception:
        try:
            import ulid
            return str(ulid.new())
        except Exception:
            import uuid
            return uuid.uuid4().hex


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Create the tenants table (root of the multi-tenancy graph).
    # ------------------------------------------------------------------
    if not _has_table("tenants"):
        op.create_table(
            "tenants",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("slug", sa.String(length=80), nullable=False, unique=True, index=True),
            sa.Column("plan", sa.String(length=20), server_default="evaluation", nullable=False),
            sa.Column("status", sa.String(length=20), server_default="active", nullable=False, index=True),
            sa.Column("trial_ends_at", sa.DateTime(timezone=True)),
            sa.Column("settings", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("primary_contact_email", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("timezone", sa.String(length=60), server_default="UTC", nullable=False),
            sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 2. Create the tenant_invites table (used by /tenants/me/users/invite).
    # ------------------------------------------------------------------
    if not _has_table("tenant_invites"):
        op.create_table(
            "tenant_invites",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("tenant_id", sa.String(length=32), nullable=False, index=True),
            sa.Column("email", sa.String(length=255), nullable=False, index=True),
            sa.Column("role", sa.String(length=40), server_default="Employee", nullable=False),
            sa.Column("token", sa.String(length=80), nullable=False, unique=True, index=True),
            sa.Column("status", sa.String(length=16), server_default="pending", nullable=False, index=True),
            sa.Column("invited_by_id", sa.String(length=32)),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 3. Seed the Default Tenant — every pre-existing row backfills to it.
    # If a row with slug="default" already exists (idempotent re-run), reuse
    # its id instead of creating a duplicate.
    # ------------------------------------------------------------------
    existing = bind.execute(sa.text("SELECT id FROM tenants WHERE slug = 'default'")).first()
    if existing:
        default_tenant_id = existing[0]
    else:
        default_tenant_id = _ulid()
        bind.execute(
            sa.text(
                "INSERT INTO tenants (id, name, slug, plan, status, settings, "
                "primary_contact_email, timezone, currency, created_at, updated_at) "
                "VALUES (:id, :name, :slug, :plan, :status, :settings, :email, :tz, :ccy, :ts, :ts)"
            ),
            {
                "id": default_tenant_id,
                "name": "Default Tenant",
                "slug": "default",
                "plan": "evaluation",
                "status": "active",
                "settings": "{}",
                "email": "admin@local",
                "tz": "UTC",
                "ccy": "USD",
                "ts": datetime.now(timezone.utc),
            },
        )

    # ------------------------------------------------------------------
    # 4. Add tenant_id to every business table + backfill + constrain.
    # Order: (a) add column nullable, (b) UPDATE … SET tenant_id = default,
    # (c) ALTER … SET NOT NULL, (d) add FK + index. Wrapped in batch alter
    # so SQLite recreates the table when needed.
    # ------------------------------------------------------------------
    for table in TENANT_SCOPED_TABLES:
        if not _has_table(table):
            # Table not in this install (e.g. an optional feature pack was
            # never created). Skip — when it's eventually created via
            # Base.metadata.create_all, the column will already be present.
            continue
        if _has_column(table, "tenant_id"):
            # Already present (re-run, or new DB created from the
            # tenant-aware metadata). Make sure the FK + NOT NULL exists,
            # but don't try to add the column again.
            _ensure_tenant_id_backfilled(bind, table, default_tenant_id)
            continue

        # (a) Add the column nullable so the backfill can populate it.
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("tenant_id", sa.String(length=32), nullable=True))

        # (b) Backfill — every existing row goes to the default tenant.
        bind.execute(
            sa.text(f"UPDATE {table} SET tenant_id = :tid WHERE tenant_id IS NULL"),
            {"tid": default_tenant_id},
        )

        # (c) + (d) NOT NULL, FK, index. Note: SQLite ALTER doesn't let us
        # change NOT NULL in-place — batch_alter_table recreates the
        # table for us when running on SQLite.
        with op.batch_alter_table(table) as batch:
            batch.alter_column("tenant_id", existing_type=sa.String(length=32), nullable=False)
            batch.create_index(
                f"ix_{table}_tenant_id",
                ["tenant_id"],
                unique=False,
            )
            batch.create_foreign_key(
                f"fk_{table}_tenant_id_tenants",
                "tenants",
                ["tenant_id"],
                ["id"],
                ondelete="CASCADE",
            )


def _ensure_tenant_id_backfilled(bind, table: str, default_tenant_id: str) -> None:
    """For an already-tenant-aware install, fill in any leftover NULLs.

    Belt-and-braces: ``Base.metadata.create_all`` creates the column with
    NOT NULL already, so this is mostly a defensive cleanup.
    """
    try:
        bind.execute(
            sa.text(f"UPDATE {table} SET tenant_id = :tid WHERE tenant_id IS NULL"),
            {"tid": default_tenant_id},
        )
    except Exception:
        # If the table genuinely has no rows or the column already enforces
        # NOT NULL with a server default, this is a no-op.
        pass


def downgrade() -> None:
    """Remove tenant_id from every business table, drop the tenants table.

    This is a destructive, lossy downgrade — multiple tenants' data
    flattens into a single soup. Only use on a dev install you're willing
    to wipe.
    """
    for table in reversed(TENANT_SCOPED_TABLES):
        if not _has_table(table) or not _has_column(table, "tenant_id"):
            continue
        with op.batch_alter_table(table) as batch:
            # Drop FK before column on databases that enforce it.
            try:
                batch.drop_constraint(f"fk_{table}_tenant_id_tenants", type_="foreignkey")
            except Exception:
                pass
            try:
                batch.drop_index(f"ix_{table}_tenant_id")
            except Exception:
                pass
            batch.drop_column("tenant_id")

    if _has_table("tenant_invites"):
        op.drop_table("tenant_invites")
    if _has_table("tenants"):
        op.drop_table("tenants")
