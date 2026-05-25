"""Academic module deepening — adds workflow columns and tracking tables.

New columns:
    - ``academic_lms_resources.download_count`` (Integer, default 0) — drives
      the "popular resources" and download-counter endpoints in the LMS UI.

New tables:
    - ``academic_study_quiz_attempts`` — records a student's MCQ attempt at a
      study note (score / total / taken_at). Feeds the quiz-history view.
    - ``academic_student_budgets`` — per-student monthly category budgets that
      power the "over budget by X" warnings on the finance dashboard.

Idempotent: every operation is guarded so the migration can re-run safely
against a database where ``Base.metadata.create_all`` already created the
tables (which is how the test suite bootstraps).

Revision ID: 0011_academic_deepening
Revises: 0010_academic
Create Date: 2026-05-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0011_academic_deepening"
down_revision: str | None = "0010_academic"
branch_labels: str | None = None
depends_on: str | None = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return any(c["name"] == column for c in _inspector().get_columns(table))


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. LMS resources — download counter
    # ------------------------------------------------------------------
    if _has_table("academic_lms_resources") and not _has_column(
        "academic_lms_resources", "download_count",
    ):
        with op.batch_alter_table("academic_lms_resources") as batch:
            batch.add_column(
                sa.Column(
                    "download_count", sa.Integer,
                    server_default="0", nullable=False,
                )
            )

    # ------------------------------------------------------------------
    # 2. Quiz attempts (study aids)
    # ------------------------------------------------------------------
    if not _has_table("academic_study_quiz_attempts"):
        op.create_table(
            "academic_study_quiz_attempts",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "note_id", sa.String(length=32),
                sa.ForeignKey(
                    "academic_study_notes.id", ondelete="CASCADE",
                ),
                nullable=False, index=True,
            ),
            sa.Column(
                "student_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("score", sa.Integer, server_default="0", nullable=False),
            sa.Column("total", sa.Integer, server_default="0", nullable=False),
            sa.Column(
                "taken_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
        )

    # ------------------------------------------------------------------
    # 3. Student monthly budgets (per-category)
    # ------------------------------------------------------------------
    if not _has_table("academic_student_budgets"):
        op.create_table(
            "academic_student_budgets",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "student_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "category", sa.String(length=120),
                nullable=False, index=True,
            ),
            sa.Column(
                "monthly_limit", sa.Numeric(12, 2), nullable=False,
            ),
            sa.Column(
                "currency", sa.String(length=3),
                server_default="USD", nullable=False,
            ),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.UniqueConstraint(
                "student_id", "category",
                name="uq_academic_student_budget_student_category",
            ),
        )


def downgrade() -> None:
    if _has_table("academic_student_budgets"):
        op.drop_table("academic_student_budgets")
    if _has_table("academic_study_quiz_attempts"):
        op.drop_table("academic_study_quiz_attempts")
    if _has_column("academic_lms_resources", "download_count"):
        with op.batch_alter_table("academic_lms_resources") as batch:
            batch.drop_column("download_count")
