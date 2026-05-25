"""Academic Module Pack — semesters, rooms, classes/enrollments, attendance,
timetable slots, LMS resources, lab reports, exams, advising sessions,
group projects + assignments, study notes, study profiles + matches,
student finance + scholarships, assignment deadlines + submissions.

Also bumps the UserRole VARCHAR width on ``users.role`` from 9 to 16 so the
new ``Registrar`` (9 chars) and ``Teacher`` (7 chars) values fit without an
implicit truncation — Admin / Manager / Employee / Developer all fit in 9
already, but Registrar was right on the edge and a wider column makes future
role additions a no-op.

Idempotent: every ``op.create_table`` is wrapped in a ``_has_table`` guard so
a fresh DB built via ``Base.metadata.create_all`` (which already created the
tables) can still be stamped + upgraded without errors.

Note on the CHECK constraint: SQLAlchemy's ``Enum`` uses
``create_constraint=False`` by default, so the ``users.role`` column is a
plain ``VARCHAR`` on both SQLite and PostgreSQL in this project — there is
no CHECK to drop. Postgres deployments would only use a real ``enum`` type
if a future migration explicitly created one; if/when that happens, this
file would need an ``ALTER TYPE`` block to add the new role labels. For the
SQLite-backed default path, widening the column is the only ``users``
change required.

Revision ID: 0010_academic
Revises: 0009_marketing
Create Date: 2026-05-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0010_academic"
down_revision: str | None = "0009_marketing"
branch_labels: str | None = None
depends_on: str | None = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _column_type_str(table: str, column: str) -> str | None:
    for col in _inspector().get_columns(table):
        if col["name"] == column:
            return str(col["type"])
    return None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Bump users.role width so the new roles (Registrar = 9 chars) fit
    #    comfortably. ``batch_alter_table`` is the idiomatic way to do an
    #    ALTER COLUMN on SQLite — it transparently rebuilds the table.
    # ------------------------------------------------------------------
    current = _column_type_str("users", "role") or ""
    if "VARCHAR(9)" in current or "VARCHAR(8)" in current:
        with op.batch_alter_table("users") as batch:
            batch.alter_column(
                "role",
                type_=sa.String(length=16),
                existing_nullable=False,
            )

    # ------------------------------------------------------------------
    # 2. Academic core (semesters + rooms)
    # ------------------------------------------------------------------
    if not _has_table("academic_semesters"):
        op.create_table(
            "academic_semesters",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False, index=True),
            sa.Column("start_date", sa.Date, nullable=False),
            sa.Column("end_date", sa.Date, nullable=False),
            sa.Column("is_current", sa.Boolean,
                      server_default=sa.text("0"), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("academic_rooms"):
        op.create_table(
            "academic_rooms",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False, index=True),
            sa.Column("building", sa.String(length=120), nullable=True),
            sa.Column("capacity", sa.Integer, server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 3. Classes + enrollments
    # ------------------------------------------------------------------
    if not _has_table("academic_classes"):
        op.create_table(
            "academic_classes",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("name", sa.String(length=180), nullable=False, index=True),
            sa.Column("course_code", sa.String(length=60), nullable=False, index=True),
            sa.Column(
                "teacher_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "semester_id", sa.String(length=32),
                sa.ForeignKey("academic_semesters.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("credit_hours", sa.Integer, server_default="3", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("academic_class_enrollments"):
        op.create_table(
            "academic_class_enrollments",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "class_id", sa.String(length=32),
                sa.ForeignKey("academic_classes.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "student_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("enrolled_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("status", sa.String(length=16),
                      server_default="active", nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint(
                "class_id", "student_id",
                name="uq_academic_enrollment_class_student",
            ),
        )

    # ------------------------------------------------------------------
    # 4. Attendance
    # ------------------------------------------------------------------
    if not _has_table("academic_attendance_records"):
        op.create_table(
            "academic_attendance_records",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "class_id", sa.String(length=32),
                sa.ForeignKey("academic_classes.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "student_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("session_date", sa.Date, nullable=False, index=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column(
                "recorded_by_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"), index=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint(
                "class_id", "student_id", "session_date",
                name="uq_academic_attendance_class_student_date",
            ),
        )

    # ------------------------------------------------------------------
    # 5. Timetable slots
    # ------------------------------------------------------------------
    if not _has_table("academic_timetable_slots"):
        op.create_table(
            "academic_timetable_slots",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "class_id", sa.String(length=32),
                sa.ForeignKey("academic_classes.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "room_id", sa.String(length=32),
                sa.ForeignKey("academic_rooms.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "semester_id", sa.String(length=32),
                sa.ForeignKey("academic_semesters.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("day_of_week", sa.Integer, nullable=False),
            sa.Column("start_time", sa.Time, nullable=False),
            sa.Column("end_time", sa.Time, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )
        op.create_index(
            "ix_academic_timetable_semester_day",
            "academic_timetable_slots",
            ["semester_id", "day_of_week"],
        )

    # ------------------------------------------------------------------
    # 6. LMS resources
    # ------------------------------------------------------------------
    if not _has_table("academic_lms_resources"):
        op.create_table(
            "academic_lms_resources",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("title", sa.String(length=300), nullable=False, index=True),
            sa.Column("description", sa.Text, server_default="", nullable=False),
            sa.Column("department", sa.String(length=120),
                      server_default="", nullable=False, index=True),
            sa.Column("semester", sa.String(length=120),
                      server_default="", nullable=False),
            sa.Column("course_code", sa.String(length=60),
                      server_default="", nullable=False, index=True),
            sa.Column("resource_type", sa.String(length=40),
                      nullable=False, index=True),
            sa.Column("file_path", sa.String(length=500), nullable=True),
            sa.Column("url", sa.String(length=500), nullable=True),
            sa.Column(
                "uploaded_by_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"), index=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 7. Lab reports
    # ------------------------------------------------------------------
    if not _has_table("academic_lab_reports"):
        op.create_table(
            "academic_lab_reports",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "student_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "class_id", sa.String(length=32),
                sa.ForeignKey("academic_classes.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("title", sa.String(length=300), nullable=False),
            sa.Column("body", sa.Text, server_default="", nullable=False),
            sa.Column("submitted_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("grade", sa.String(length=16), nullable=True),
            sa.Column("feedback", sa.Text, nullable=True),
            sa.Column("status", sa.String(length=16),
                      server_default="draft", nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 8. Exams
    # ------------------------------------------------------------------
    if not _has_table("academic_exams"):
        op.create_table(
            "academic_exams",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("course_code", sa.String(length=60), nullable=False, index=True),
            sa.Column("exam_date", sa.Date, nullable=False, index=True),
            sa.Column("start_time", sa.Time, nullable=False),
            sa.Column("duration_min", sa.Integer, server_default="120", nullable=False),
            sa.Column(
                "room_id", sa.String(length=32),
                sa.ForeignKey("academic_rooms.id", ondelete="SET NULL"), index=True,
            ),
            sa.Column("syllabus_topics", sa.JSON, nullable=False),
            sa.Column("difficulty", sa.String(length=16),
                      server_default="medium", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 9. Advising
    # ------------------------------------------------------------------
    if not _has_table("academic_advising_sessions"):
        op.create_table(
            "academic_advising_sessions",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "student_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "advisor_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("scheduled_at", sa.DateTime(timezone=True),
                      nullable=False, index=True),
            sa.Column("notes", sa.Text, server_default="", nullable=False),
            sa.Column("current_cgpa", sa.Numeric(4, 2), nullable=True),
            sa.Column("target_cgpa", sa.Numeric(4, 2), nullable=True),
            sa.Column("credits_completed", sa.Integer,
                      server_default="0", nullable=False),
            sa.Column("credits_remaining", sa.Integer,
                      server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 10. Group projects
    # ------------------------------------------------------------------
    if not _has_table("academic_group_projects"):
        op.create_table(
            "academic_group_projects",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("name", sa.String(length=300), nullable=False, index=True),
            sa.Column(
                "class_id", sa.String(length=32),
                sa.ForeignKey("academic_classes.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("description", sa.Text, server_default="", nullable=False),
            sa.Column("deadline", sa.DateTime(timezone=True),
                      nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("academic_group_project_assignments"):
        op.create_table(
            "academic_group_project_assignments",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "project_id", sa.String(length=32),
                sa.ForeignKey("academic_group_projects.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "student_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("role", sa.String(length=120),
                      server_default="", nullable=False),
            sa.Column("weight", sa.Numeric(4, 2),
                      server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 11. Study aids
    # ------------------------------------------------------------------
    if not _has_table("academic_study_notes"):
        op.create_table(
            "academic_study_notes",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "student_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("source_text", sa.Text, server_default="", nullable=False),
            sa.Column("summary", sa.Text, server_default="", nullable=False),
            sa.Column("flashcards", sa.JSON, nullable=False),
            sa.Column("mcqs", sa.JSON, nullable=False),
            sa.Column("source_type", sa.String(length=16),
                      server_default="paste", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 12. Study match
    # ------------------------------------------------------------------
    if not _has_table("academic_study_profiles"):
        op.create_table(
            "academic_study_profiles",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "student_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False, unique=True, index=True,
            ),
            sa.Column("university", sa.String(length=180),
                      server_default="", nullable=False),
            sa.Column("department", sa.String(length=120),
                      server_default="", nullable=False),
            sa.Column("semester", sa.String(length=60),
                      server_default="", nullable=False),
            sa.Column("courses", sa.JSON, nullable=False),
            sa.Column("goals", sa.Text, server_default="", nullable=False),
            sa.Column("preferred_time", sa.String(length=60),
                      server_default="", nullable=False),
            sa.Column("study_style", sa.String(length=60),
                      server_default="", nullable=False),
            sa.Column("online_only", sa.Boolean,
                      server_default=sa.text("0"), nullable=False),
            sa.Column("is_public", sa.Boolean,
                      server_default=sa.text("1"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("academic_study_group_matches"):
        op.create_table(
            "academic_study_group_matches",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "student_a_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "student_b_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("score", sa.Integer, server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint(
                "student_a_id", "student_b_id",
                name="uq_academic_study_match_pair",
            ),
        )

    # ------------------------------------------------------------------
    # 13. Student finance + scholarships
    # ------------------------------------------------------------------
    if not _has_table("academic_student_finance_records"):
        op.create_table(
            "academic_student_finance_records",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "student_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("kind", sa.String(length=24), nullable=False, index=True),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(length=3),
                      server_default="USD", nullable=False),
            sa.Column("occurred_on", sa.Date, nullable=False, index=True),
            sa.Column("category", sa.String(length=120),
                      server_default="", nullable=False, index=True),
            sa.Column("note", sa.Text, server_default="", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("academic_scholarships"):
        op.create_table(
            "academic_scholarships",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("name", sa.String(length=300), nullable=False, index=True),
            sa.Column("provider", sa.String(length=180),
                      server_default="", nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(length=3),
                      server_default="USD", nullable=False),
            sa.Column("eligibility", sa.Text, server_default="", nullable=False),
            sa.Column("deadline", sa.Date, nullable=True, index=True),
            sa.Column("url", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 14. Deadlines (assignments + submissions)
    # ------------------------------------------------------------------
    if not _has_table("academic_assignments"):
        op.create_table(
            "academic_assignments",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "class_id", sa.String(length=32),
                sa.ForeignKey("academic_classes.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("title", sa.String(length=300), nullable=False, index=True),
            sa.Column("description", sa.Text, server_default="", nullable=False),
            sa.Column("deadline", sa.DateTime(timezone=True),
                      nullable=False, index=True),
            sa.Column("weight", sa.Numeric(4, 2),
                      server_default="0", nullable=False),
            sa.Column("submission_link", sa.String(length=500),
                      server_default="", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("academic_assignment_submissions"):
        op.create_table(
            "academic_assignment_submissions",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "assignment_id", sa.String(length=32),
                sa.ForeignKey("academic_assignments.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "student_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("submitted_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("status", sa.String(length=16),
                      server_default="not_started", nullable=False, index=True),
            sa.Column("word_count", sa.Integer,
                      server_default="0", nullable=False),
            sa.Column("submission_url", sa.String(length=500),
                      server_default="", nullable=False),
            sa.Column("notes", sa.Text, server_default="", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint(
                "assignment_id", "student_id",
                name="uq_academic_submission_assignment_student",
            ),
        )


def downgrade() -> None:
    # Drop child tables before parents (FK ordering matters).
    for tbl in (
        "academic_assignment_submissions", "academic_assignments",
        "academic_scholarships", "academic_student_finance_records",
        "academic_study_group_matches", "academic_study_profiles",
        "academic_study_notes",
        "academic_group_project_assignments", "academic_group_projects",
        "academic_advising_sessions", "academic_exams",
        "academic_lab_reports", "academic_lms_resources",
        "academic_timetable_slots",
        "academic_attendance_records",
        "academic_class_enrollments", "academic_classes",
        "academic_rooms", "academic_semesters",
    ):
        if _has_table(tbl):
            op.drop_table(tbl)
