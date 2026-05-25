"""Lab reports — students manage their own; teacher/admin view + grade.

Owner isolation: a student can only see their own reports. Teacher/admin can
filter by class to see every submission. The grade endpoint flips the row
into ``status="graded"`` and stamps the teacher's feedback.

Workflow features layered on top of the CRUD scaffold:
- ``POST /lab/reports/{id}/submit`` — student transitions a draft to
  submitted, stamps the submitted_at timestamp, refuses re-submission.
- ``POST /lab/reports/{id}/grade`` — teacher grades + writes feedback (was
  already on the scaffold; kept untouched here).
- ``GET /lab/classes/{class_id}/pending`` — teacher's grading queue.
- ``GET /lab/students/me/summary`` — per-class rollup for the student
  dashboard (count by status + averaged numeric grade).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.academic._common import (
    TEACHER_OR_ADMIN, _apply_update, _get_or_404, require_any_role,
)
from app.core.exceptions import ConflictError, NotFoundError
from app.db.session import get_db
from app.models.academic.lab_reports import AcademicLabReport
from app.models.user import User, UserRole
from app.schemas.academic.lab_reports import (
    LabReportClassSummaryRow, LabReportCreate, LabReportGrade, LabReportOut,
    LabReportStudentSummary, LabReportUpdate,
)

router = APIRouter()


def _is_staff(role) -> bool:
    return role in {
        UserRole.admin, UserRole.manager, UserRole.teacher,
    }


@router.get("/reports", response_model=list[LabReportOut])
def list_reports(
    class_id: str | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Students see their own reports; staff see everyone's. ``class_id`` is a
    filter both can use (staff to focus on one section, students to find one
    of their own)."""
    stmt = select(AcademicLabReport).order_by(
        AcademicLabReport.submitted_at.desc()
    )
    if not _is_staff(current.role):
        stmt = stmt.where(AcademicLabReport.student_id == current.id)
    if class_id:
        stmt = stmt.where(AcademicLabReport.class_id == class_id)
    return db.scalars(stmt).all()


@router.post(
    "/reports",
    response_model=LabReportOut,
    status_code=status.HTTP_201_CREATED,
)
def create_report(
    payload: LabReportCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = AcademicLabReport(student_id=current.id, **payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# ---------------------------------------------------------------------------
# Workflow endpoints — pending / summary / submit need to live BEFORE the
# /reports/{report_id} routes so the dynamic segment doesn't swallow them.
# ---------------------------------------------------------------------------
@router.get(
    "/classes/{class_id}/pending",
    response_model=list[LabReportOut],
    dependencies=[Depends(require_any_role(*TEACHER_OR_ADMIN))],
)
def pending_reports_for_class(
    class_id: str,
    db: Session = Depends(get_db),
):
    """Teacher's grading queue: every submitted-but-not-graded report in a class."""
    return db.scalars(
        select(AcademicLabReport)
        .where(
            AcademicLabReport.class_id == class_id,
            AcademicLabReport.status == "submitted",
        )
        .order_by(AcademicLabReport.submitted_at)
    ).all()


@router.get(
    "/students/me/summary",
    response_model=LabReportStudentSummary,
)
def my_summary(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Per-class rollup for the signed-in student.

    Numeric grades (e.g. "85", "92.5") feed into ``avg_numeric_grade``; non
    -numeric grades (e.g. "A", "Pass") are recorded in the status counts but
    deliberately excluded from the average so the number stays meaningful.
    """
    rows = db.scalars(
        select(AcademicLabReport)
        .where(AcademicLabReport.student_id == current.id)
    ).all()
    by_class: dict[str, list[AcademicLabReport]] = defaultdict(list)
    for r in rows:
        by_class[r.class_id].append(r)
    summary_rows: list[LabReportClassSummaryRow] = []
    for class_id, items in by_class.items():
        by_status: dict[str, int] = defaultdict(int)
        numeric_grades: list[float] = []
        for item in items:
            by_status[item.status or "draft"] += 1
            if item.grade:
                try:
                    numeric_grades.append(float(item.grade))
                except (TypeError, ValueError):
                    pass
        avg = (
            round(sum(numeric_grades) / len(numeric_grades), 2)
            if numeric_grades else None
        )
        summary_rows.append(
            LabReportClassSummaryRow(
                class_id=class_id,
                total=len(items),
                by_status=dict(by_status),
                avg_numeric_grade=avg,
            )
        )
    summary_rows.sort(key=lambda x: x.class_id)
    return LabReportStudentSummary(
        student_id=current.id, classes=summary_rows,
    )


@router.post(
    "/reports/{report_id}/submit",
    response_model=LabReportOut,
)
def submit_report(
    report_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Owner transitions a draft into ``submitted`` and stamps the time.

    Refuses a second submit so a graded report can't be reset by accident.
    """
    obj = _get_or_404(db, AcademicLabReport, report_id, "Lab report")
    if obj.student_id != current.id and not _is_staff(current.role):
        raise NotFoundError("Lab report not found")
    if obj.status in {"submitted", "graded"}:
        raise ConflictError(
            f"Lab report is already in '{obj.status}' state; cannot submit again."
        )
    obj.status = "submitted"
    obj.submitted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/reports/{report_id}", response_model=LabReportOut)
def get_report(
    report_id: str, db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = _get_or_404(db, AcademicLabReport, report_id, "Lab report")
    if obj.student_id != current.id and not _is_staff(current.role):
        # Don't leak existence to other students.
        raise NotFoundError("Lab report not found")
    return obj


@router.patch("/reports/{report_id}", response_model=LabReportOut)
def update_report(
    report_id: str, payload: LabReportUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = _get_or_404(db, AcademicLabReport, report_id, "Lab report")
    if obj.student_id != current.id and not _is_staff(current.role):
        raise NotFoundError("Lab report not found")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT,
)
def delete_report(
    report_id: str, db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = _get_or_404(db, AcademicLabReport, report_id, "Lab report")
    if obj.student_id != current.id and not _is_staff(current.role):
        raise NotFoundError("Lab report not found")
    db.delete(obj)
    db.commit()


@router.post(
    "/reports/{report_id}/grade",
    response_model=LabReportOut,
    dependencies=[Depends(require_any_role(*TEACHER_OR_ADMIN))],
)
def grade_report(
    report_id: str, payload: LabReportGrade, db: Session = Depends(get_db),
):
    obj = _get_or_404(db, AcademicLabReport, report_id, "Lab report")
    obj.grade = payload.grade
    obj.feedback = payload.feedback
    obj.status = "graded"
    db.commit()
    db.refresh(obj)
    return obj
