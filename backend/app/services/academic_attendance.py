"""Attendance — bulk-mark, per-student summary, class report.

Endpoints in ``app/api/v1/endpoints/academic/attendance.py`` call into these
helpers, so the test surface stays small and framework-free (no FastAPI
imports here).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.academic.attendance import AcademicAttendanceRecord

# Allowed values for the ``status`` column. Kept in code rather than as a DB
# CHECK so adding a new status (eg. "remote") is a one-line schema change.
ALLOWED_STATUSES: tuple[str, ...] = ("present", "absent", "late", "excused")


def mark_attendance(
    db: Session,
    *,
    class_id: str,
    session_date: date,
    records: list[dict],
    recorded_by_id: str | None,
) -> list[AcademicAttendanceRecord]:
    """Upsert attendance for a whole class session.

    ``records`` is a list of ``{"student_id": str, "status": str}`` dicts.
    Existing rows for the same ``(class_id, student_id, session_date)`` are
    overwritten in place so a teacher can correct a mark by re-submitting the
    whole roster.
    """
    if not records:
        return []

    # Load any existing rows for this (class, date) so we can overwrite rather
    # than violate the unique constraint. Single round-trip vs. one per row.
    existing = {
        r.student_id: r
        for r in db.scalars(
            select(AcademicAttendanceRecord)
            .where(
                AcademicAttendanceRecord.class_id == class_id,
                AcademicAttendanceRecord.session_date == session_date,
            )
        ).all()
    }

    out: list[AcademicAttendanceRecord] = []
    for rec in records:
        student_id = rec["student_id"]
        status = rec["status"]
        if status not in ALLOWED_STATUSES:
            # Be loud about a bad status — easier to debug than a silent skip.
            raise ValueError(
                f"Invalid attendance status {status!r}; "
                f"expected one of {ALLOWED_STATUSES}"
            )
        row = existing.get(student_id)
        if row is None:
            row = AcademicAttendanceRecord(
                class_id=class_id,
                student_id=student_id,
                session_date=session_date,
                status=status,
                recorded_by_id=recorded_by_id,
            )
            db.add(row)
        else:
            row.status = status
            row.recorded_by_id = recorded_by_id
        out.append(row)

    db.commit()
    for row in out:
        db.refresh(row)
    return out


def class_attendance_for_session(
    db: Session, *, class_id: str, session_date: date,
) -> list[AcademicAttendanceRecord]:
    """All attendance rows for one class on one date."""
    return db.scalars(
        select(AcademicAttendanceRecord)
        .where(
            AcademicAttendanceRecord.class_id == class_id,
            AcademicAttendanceRecord.session_date == session_date,
        )
        .order_by(AcademicAttendanceRecord.student_id)
    ).all()


def _summary_from_rows(
    student_id: str, rows: list[AcademicAttendanceRecord],
) -> dict:
    """Convert a per-student row set into the summary shape."""
    counts = {"present": 0, "absent": 0, "late": 0, "excused": 0}
    for r in rows:
        if r.status in counts:
            counts[r.status] += 1
    total = sum(counts.values())
    pct = (counts["present"] / total * 100.0) if total else 0.0
    return {
        "student_id": student_id,
        "present": counts["present"],
        "absent": counts["absent"],
        "late": counts["late"],
        "excused": counts["excused"],
        "total": total,
        # Round to one decimal so the API surface is human-friendly without
        # forcing the caller to do display formatting.
        "percentage": round(pct, 1),
    }


def student_attendance_summary(
    db: Session, *, student_id: str, class_id: str | None = None,
) -> dict:
    """Counts + present-percentage for one student.

    When ``class_id`` is None the summary is across every class the student
    has been marked in. Useful for the student's own dashboard.
    """
    stmt = select(AcademicAttendanceRecord).where(
        AcademicAttendanceRecord.student_id == student_id,
    )
    if class_id:
        stmt = stmt.where(AcademicAttendanceRecord.class_id == class_id)
    rows = db.scalars(stmt).all()
    return _summary_from_rows(student_id, rows)


def class_attendance_report(
    db: Session, *, class_id: str,
) -> dict:
    """Per-student rollup for one class — what the teacher's report renders."""
    rows = db.scalars(
        select(AcademicAttendanceRecord)
        .where(AcademicAttendanceRecord.class_id == class_id)
        .order_by(AcademicAttendanceRecord.student_id)
    ).all()

    grouped: dict[str, list[AcademicAttendanceRecord]] = defaultdict(list)
    for r in rows:
        grouped[r.student_id].append(r)

    students = [
        _summary_from_rows(sid, srows) for sid, srows in grouped.items()
    ]
    # Stable order so successive calls render the same — the dict insertion
    # order from defaultdict already matches the SQL order_by, but be explicit.
    students.sort(key=lambda s: s["student_id"])
    return {"class_id": class_id, "students": students}


def student_records_across_classes(
    db: Session, *, student_id: str,
) -> list[AcademicAttendanceRecord]:
    """Every attendance row for a student — fed to the student's "my attendance"
    view, which then groups by class on the client."""
    return db.scalars(
        select(AcademicAttendanceRecord)
        .where(AcademicAttendanceRecord.student_id == student_id)
        .order_by(AcademicAttendanceRecord.session_date.desc())
    ).all()
