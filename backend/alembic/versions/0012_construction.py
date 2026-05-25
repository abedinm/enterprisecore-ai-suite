"""Construction Project Management — projects, risks, schedule tasks +
dependencies, milestones, progress reports, permits, site instructions,
variations, EOT requests, contracts, RACI entries, insurances, toolbox talks.

The construction module backs the flagship feature of the +Verticals SKU
(and ships free under +EDU / +Evaluation per app/core/plans.py). All tables
are prefixed ``construction_*``; ``construction_projects`` optionally
references the always-on ``projects`` table via ``generic_project_id`` so a
customer can pair a generic project shell with construction-specific data
without duplicating the record.

Idempotent: every ``op.create_table`` is wrapped in a ``_has_table`` guard so
a fresh DB built via ``Base.metadata.create_all`` (which already created the
tables) can still be stamped + upgraded without errors.

Revision ID: 0012_construction
Revises: 0011_academic_deepening
Create Date: 2026-05-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0012_construction"
down_revision: str | None = "0011_academic_deepening"
branch_labels: str | None = None
depends_on: str | None = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Construction projects (root of the module's FK tree)
    # ------------------------------------------------------------------
    if not _has_table("construction_projects"):
        op.create_table(
            "construction_projects",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "generic_project_id", sa.String(length=32),
                sa.ForeignKey("projects.id", ondelete="SET NULL"),
                index=True,
            ),
            sa.Column("name", sa.String(length=200), nullable=False, index=True),
            sa.Column("client_name", sa.String(length=200),
                      server_default="", nullable=False),
            sa.Column("location", sa.String(length=300),
                      server_default="", nullable=False),
            sa.Column("project_type", sa.String(length=24),
                      nullable=False, index=True),
            sa.Column("contract_value", sa.Numeric(14, 2),
                      server_default="0", nullable=False),
            sa.Column("currency", sa.String(length=3),
                      server_default="USD", nullable=False),
            sa.Column("start_date", sa.Date, nullable=True),
            sa.Column("expected_end_date", sa.Date, nullable=True),
            sa.Column("actual_end_date", sa.Date, nullable=True),
            sa.Column("status", sa.String(length=24),
                      server_default="planning", nullable=False, index=True),
            sa.Column("description", sa.Text,
                      server_default="", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 2. Risks
    # ------------------------------------------------------------------
    if not _has_table("construction_risks"):
        op.create_table(
            "construction_risks",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "construction_project_id", sa.String(length=32),
                sa.ForeignKey("construction_projects.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("title", sa.String(length=300),
                      nullable=False, index=True),
            sa.Column("description", sa.Text,
                      server_default="", nullable=False),
            sa.Column("category", sa.String(length=24),
                      server_default="safety", nullable=False, index=True),
            sa.Column("probability", sa.Integer,
                      server_default="1", nullable=False),
            sa.Column("impact", sa.Integer,
                      server_default="1", nullable=False),
            sa.Column("score", sa.Integer,
                      server_default="1", nullable=False, index=True),
            sa.Column("mitigation_plan", sa.Text,
                      server_default="", nullable=False),
            sa.Column(
                "owner_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                index=True,
            ),
            sa.Column("status", sa.String(length=16),
                      server_default="open", nullable=False, index=True),
            sa.Column("identified_at", sa.DateTime(timezone=True),
                      nullable=True),
            sa.Column("due_date", sa.Date, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 3. Schedule tasks (WBS)
    # ------------------------------------------------------------------
    if not _has_table("construction_schedule_tasks"):
        op.create_table(
            "construction_schedule_tasks",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "construction_project_id", sa.String(length=32),
                sa.ForeignKey("construction_projects.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("name", sa.String(length=300),
                      nullable=False, index=True),
            sa.Column("description", sa.Text,
                      server_default="", nullable=False),
            sa.Column(
                "parent_task_id", sa.String(length=32),
                sa.ForeignKey(
                    "construction_schedule_tasks.id", ondelete="SET NULL",
                ),
                index=True,
            ),
            sa.Column("start_date", sa.Date, nullable=True),
            sa.Column("end_date", sa.Date, nullable=True),
            sa.Column("duration_days", sa.Integer,
                      server_default="0", nullable=False),
            sa.Column(
                "assigned_to_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                index=True,
            ),
            sa.Column("progress_percent", sa.Integer,
                      server_default="0", nullable=False),
            sa.Column("status", sa.String(length=16),
                      server_default="not_started", nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 4. Schedule dependencies (Gantt edges)
    # ------------------------------------------------------------------
    if not _has_table("construction_schedule_dependencies"):
        op.create_table(
            "construction_schedule_dependencies",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "predecessor_id", sa.String(length=32),
                sa.ForeignKey(
                    "construction_schedule_tasks.id", ondelete="CASCADE",
                ),
                nullable=False, index=True,
            ),
            sa.Column(
                "successor_id", sa.String(length=32),
                sa.ForeignKey(
                    "construction_schedule_tasks.id", ondelete="CASCADE",
                ),
                nullable=False, index=True,
            ),
            sa.Column("dependency_type", sa.String(length=16),
                      server_default="finish_start", nullable=False),
            sa.Column("lag_days", sa.Integer,
                      server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 5. Milestones
    # ------------------------------------------------------------------
    if not _has_table("construction_milestones"):
        op.create_table(
            "construction_milestones",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "construction_project_id", sa.String(length=32),
                sa.ForeignKey("construction_projects.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("name", sa.String(length=300),
                      nullable=False, index=True),
            sa.Column("planned_date", sa.Date, nullable=False, index=True),
            sa.Column("actual_date", sa.Date, nullable=True),
            sa.Column("status", sa.String(length=16),
                      server_default="upcoming", nullable=False, index=True),
            sa.Column("payment_trigger", sa.Boolean,
                      server_default=sa.text("0"), nullable=False),
            sa.Column("payment_amount", sa.Numeric(14, 2), nullable=True),
            sa.Column("notes", sa.Text,
                      server_default="", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 6. Progress reports
    # ------------------------------------------------------------------
    if not _has_table("construction_progress_reports"):
        op.create_table(
            "construction_progress_reports",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "construction_project_id", sa.String(length=32),
                sa.ForeignKey("construction_projects.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("report_date", sa.Date, nullable=False, index=True),
            sa.Column("overall_progress_percent", sa.Integer,
                      server_default="0", nullable=False),
            sa.Column("narrative", sa.Text,
                      server_default="", nullable=False),
            sa.Column(
                "reported_by_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                index=True,
            ),
            sa.Column("photos", sa.JSON, nullable=False),
            sa.Column("weather_conditions", sa.String(length=120),
                      server_default="", nullable=False),
            sa.Column("workforce_count", sa.Integer,
                      server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 7. Permits
    # ------------------------------------------------------------------
    if not _has_table("construction_permits"):
        op.create_table(
            "construction_permits",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "construction_project_id", sa.String(length=32),
                sa.ForeignKey("construction_projects.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("permit_type", sa.String(length=120),
                      server_default="", nullable=False, index=True),
            sa.Column("issuing_authority", sa.String(length=200),
                      server_default="", nullable=False),
            sa.Column("application_date", sa.Date, nullable=True),
            sa.Column("approval_date", sa.Date, nullable=True),
            sa.Column("expiry_date", sa.Date, nullable=True, index=True),
            sa.Column("status", sa.String(length=16),
                      server_default="draft", nullable=False, index=True),
            sa.Column("reference_number", sa.String(length=120),
                      server_default="", nullable=False, index=True),
            sa.Column("conditions", sa.Text,
                      server_default="", nullable=False),
            sa.Column("document_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 8. Site instructions
    # ------------------------------------------------------------------
    if not _has_table("construction_site_instructions"):
        op.create_table(
            "construction_site_instructions",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "construction_project_id", sa.String(length=32),
                sa.ForeignKey("construction_projects.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("number", sa.String(length=20),
                      nullable=False, index=True),
            sa.Column("title", sa.String(length=300), nullable=False),
            sa.Column("description", sa.Text,
                      server_default="", nullable=False),
            sa.Column(
                "issued_by_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                index=True,
            ),
            sa.Column("issued_to", sa.String(length=200),
                      server_default="", nullable=False),
            sa.Column("issued_at", sa.DateTime(timezone=True),
                      nullable=True),
            sa.Column("response_required_by", sa.Date, nullable=True),
            sa.Column("status", sa.String(length=16),
                      server_default="issued", nullable=False, index=True),
            sa.Column("response", sa.Text, nullable=True),
            sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint(
                "construction_project_id", "number",
                name="uq_construction_si_project_number",
            ),
        )

    # ------------------------------------------------------------------
    # 9. Variations
    # ------------------------------------------------------------------
    if not _has_table("construction_variations"):
        op.create_table(
            "construction_variations",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "construction_project_id", sa.String(length=32),
                sa.ForeignKey("construction_projects.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("number", sa.String(length=20),
                      nullable=False, index=True),
            sa.Column("title", sa.String(length=300), nullable=False),
            sa.Column("description", sa.Text,
                      server_default="", nullable=False),
            sa.Column("requested_by", sa.String(length=200),
                      server_default="", nullable=False),
            sa.Column("cost_impact", sa.Numeric(14, 2),
                      server_default="0", nullable=False),
            sa.Column("time_impact_days", sa.Integer,
                      server_default="0", nullable=False),
            sa.Column("status", sa.String(length=16),
                      server_default="pending", nullable=False, index=True),
            sa.Column("justification", sa.Text,
                      server_default="", nullable=False),
            sa.Column("submitted_at", sa.DateTime(timezone=True),
                      nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True),
                      nullable=True),
            sa.Column(
                "decided_by_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                index=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint(
                "construction_project_id", "number",
                name="uq_construction_var_project_number",
            ),
        )

    # ------------------------------------------------------------------
    # 10. EOT requests
    # ------------------------------------------------------------------
    if not _has_table("construction_eot_requests"):
        op.create_table(
            "construction_eot_requests",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "construction_project_id", sa.String(length=32),
                sa.ForeignKey("construction_projects.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("requested_days", sa.Integer,
                      server_default="0", nullable=False),
            sa.Column("reason", sa.Text,
                      server_default="", nullable=False),
            sa.Column("supporting_evidence", sa.Text,
                      server_default="", nullable=False),
            sa.Column("claim_date", sa.Date, nullable=True),
            sa.Column("status", sa.String(length=16),
                      server_default="submitted", nullable=False, index=True),
            sa.Column("granted_days", sa.Integer, nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "decided_by_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                index=True,
            ),
            sa.Column("decision_notes", sa.Text,
                      server_default="", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 11. Contracts
    # ------------------------------------------------------------------
    if not _has_table("construction_contracts"):
        op.create_table(
            "construction_contracts",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "construction_project_id", sa.String(length=32),
                sa.ForeignKey("construction_projects.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("contract_number", sa.String(length=120),
                      server_default="", nullable=False, index=True),
            sa.Column("contract_type", sa.String(length=16),
                      server_default="custom", nullable=False),
            sa.Column("counterparty", sa.String(length=200),
                      server_default="", nullable=False),
            sa.Column("value", sa.Numeric(14, 2),
                      server_default="0", nullable=False),
            sa.Column("currency", sa.String(length=3),
                      server_default="USD", nullable=False),
            sa.Column("signed_date", sa.Date, nullable=True),
            sa.Column("start_date", sa.Date, nullable=True),
            sa.Column("end_date", sa.Date, nullable=True),
            sa.Column("retention_percent", sa.Numeric(5, 2),
                      server_default="0", nullable=False),
            sa.Column("defects_liability_period_days", sa.Integer,
                      server_default="0", nullable=False),
            sa.Column("payment_terms", sa.Text,
                      server_default="", nullable=False),
            sa.Column("document_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 12. RACI entries
    # ------------------------------------------------------------------
    if not _has_table("construction_raci_entries"):
        op.create_table(
            "construction_raci_entries",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "construction_project_id", sa.String(length=32),
                sa.ForeignKey("construction_projects.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("activity", sa.String(length=300),
                      nullable=False, index=True),
            sa.Column(
                "responsible_user_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                index=True,
            ),
            sa.Column(
                "accountable_user_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                index=True,
            ),
            sa.Column("consulted", sa.JSON, nullable=False),
            sa.Column("informed", sa.JSON, nullable=False),
            sa.Column("notes", sa.Text,
                      server_default="", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 13. Insurances
    # ------------------------------------------------------------------
    if not _has_table("construction_insurances"):
        op.create_table(
            "construction_insurances",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "construction_project_id", sa.String(length=32),
                sa.ForeignKey("construction_projects.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("insurance_type", sa.String(length=16),
                      server_default="other", nullable=False, index=True),
            sa.Column("provider", sa.String(length=200),
                      server_default="", nullable=False),
            sa.Column("policy_number", sa.String(length=120),
                      server_default="", nullable=False, index=True),
            sa.Column("sum_insured", sa.Numeric(14, 2),
                      server_default="0", nullable=False),
            sa.Column("currency", sa.String(length=3),
                      server_default="USD", nullable=False),
            sa.Column("start_date", sa.Date, nullable=True),
            sa.Column("expiry_date", sa.Date, nullable=True, index=True),
            sa.Column("premium_amount", sa.Numeric(14, 2),
                      server_default="0", nullable=False),
            sa.Column("renewal_reminder_days", sa.Integer,
                      server_default="30", nullable=False),
            sa.Column("document_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 14. Toolbox talks
    # ------------------------------------------------------------------
    if not _has_table("construction_toolbox_talks"):
        op.create_table(
            "construction_toolbox_talks",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "construction_project_id", sa.String(length=32),
                sa.ForeignKey("construction_projects.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("topic", sa.String(length=300),
                      nullable=False, index=True),
            sa.Column(
                "conducted_by_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                index=True,
            ),
            sa.Column("conducted_at", sa.DateTime(timezone=True),
                      nullable=True, index=True),
            sa.Column("attendees_count", sa.Integer,
                      server_default="0", nullable=False),
            sa.Column("key_points", sa.Text,
                      server_default="", nullable=False),
            sa.Column("attachments", sa.JSON, nullable=False),
            sa.Column("notes", sa.Text,
                      server_default="", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    # Drop child tables before parents (FK ordering matters).
    for tbl in (
        "construction_toolbox_talks",
        "construction_insurances",
        "construction_raci_entries",
        "construction_contracts",
        "construction_eot_requests",
        "construction_variations",
        "construction_site_instructions",
        "construction_permits",
        "construction_progress_reports",
        "construction_milestones",
        "construction_schedule_dependencies",
        "construction_schedule_tasks",
        "construction_risks",
        "construction_projects",
    ):
        if _has_table(tbl):
            op.drop_table(tbl)
