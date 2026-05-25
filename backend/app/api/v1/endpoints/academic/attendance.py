"""Attendance endpoints — mark, view session, view summary."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.academic._common import (
    TEACHER_OR_ADMIN, require_any_role,
)
from app.core.exceptions import PermissionDenied
from app.db.session import get_db
from app.models.academic.classes import AcademicClass
from app.models.user import User, UserRole
from app.schemas.academic.attendance import (
    AttendanceOut, BulkAttendanceIn, ClassAttendanceReport,
)
from app.services import academic_attendance as svc

router = APIRouter()


# ---------------------------------------------------------------------------
# Teacher / admin — mark + read
# ---------------------------------------------------------------------------
@router.post(
    "/classes/{class_id}/attendance",
    response_model=list[AttendanceOut],
    status_code=status.HTTP_201_CREATED,
)
def mark_class_attendance(
    class_id: str,
    payload: BulkAttendanceIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_any_role(*TEACHER_OR_ADMIN)),
):
    rows = svc.mark_attendance(
        db,
        class_id=class_id,
        session_date=payload.session_date,
        records=[r.model_dump() for r in payload.records],
        recorded_by_id=current.id,
    )
    return rows


@router.get(
    "/classes/{class_id}/attendance",
    response_model=list[AttendanceOut],
)
def get_class_session_attendance(
    class_id: str,
    session_date: date,
    db: Session = Depends(get_db),
    current: User = Depends(require_any_role(*TEACHER_OR_ADMIN)),
):
    return svc.class_attendance_for_session(
        db, class_id=class_id, session_date=session_date,
    )


@router.get(
    "/classes/{class_id}/attendance/report",
    response_model=ClassAttendanceReport,
)
def get_class_attendance_report(
    class_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(require_any_role(*TEACHER_OR_ADMIN)),
):
    return svc.class_attendance_report(db, class_id=class_id)


# ---------------------------------------------------------------------------
# Student — own records
# ---------------------------------------------------------------------------
@router.get(
    "/students/me/attendance",
    response_model=list[AttendanceOut],
)
def my_attendance(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """The signed-in student's own attendance across every class.

    Open to any authenticated user; the result set is filtered by the caller's
    id so a teacher visiting this URL just sees nothing (they have no
    attendance records of their own).
    """
    return svc.student_records_across_classes(db, student_id=current.id)


@router.get(
    "/students/{student_id}/attendance",
    response_model=list[AttendanceOut],
)
def student_attendance(
    student_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """One student's attendance — readable by the student themselves OR by an
    advisor/teacher/registrar/admin. The student can never see another
    student's records here; staff roles can see anyone's."""
    if current.id != student_id and current.role not in {
        UserRole.admin, UserRole.manager, UserRole.teacher,
        UserRole.registrar, UserRole.dean,
    }:
        raise PermissionDenied(
            "You may only view your own attendance unless you have a staff role.",
        )
    return svc.student_records_across_classes(db, student_id=student_id)
