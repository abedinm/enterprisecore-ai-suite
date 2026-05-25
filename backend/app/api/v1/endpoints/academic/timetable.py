"""Timetable endpoints — slot CRUD with conflict detection + schedule views.

The router included here is mounted at ``/api/v1/academic/timetable``; the
"rooms" sub-area is duplicated under this prefix for ergonomic reasons so
clients can hit ``/timetable/rooms`` instead of swinging up to ``/rooms``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.academic._common import (
    REGISTRAR_OR_ADMIN, _get_or_404, require_any_role,
)
from app.core.exceptions import PermissionDenied
from app.db.session import get_db
from app.models.academic.timetable import AcademicTimetableSlot
from app.models.user import User, UserRole
from app.schemas.academic.timetable import SlotCreate, SlotOut, SlotUpdate
from app.services import academic_timetable as svc

router = APIRouter()


# ---------------------------------------------------------------------------
# Slot CRUD
# ---------------------------------------------------------------------------
@router.get("/slots", response_model=list[SlotOut])
def list_slots(
    semester_id: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from sqlalchemy import select
    stmt = select(AcademicTimetableSlot).order_by(
        AcademicTimetableSlot.day_of_week,
        AcademicTimetableSlot.start_time,
    )
    if semester_id:
        stmt = stmt.where(AcademicTimetableSlot.semester_id == semester_id)
    return db.scalars(stmt).all()


@router.post(
    "/slots",
    response_model=SlotOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def create_slot(payload: SlotCreate, db: Session = Depends(get_db)):
    return svc.schedule_class(
        db,
        class_id=payload.class_id,
        room_id=payload.room_id,
        day_of_week=payload.day_of_week,
        start_time=payload.start_time,
        end_time=payload.end_time,
        semester_id=payload.semester_id,
    )


@router.patch(
    "/slots/{slot_id}",
    response_model=SlotOut,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def update_slot_endpoint(
    slot_id: str, payload: SlotUpdate, db: Session = Depends(get_db),
):
    slot = _get_or_404(db, AcademicTimetableSlot, slot_id, "Slot")
    return svc.update_slot(db, slot=slot, payload=payload.model_dump(exclude_unset=True))


@router.delete(
    "/slots/{slot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def delete_slot(slot_id: str, db: Session = Depends(get_db)):
    slot = _get_or_404(db, AcademicTimetableSlot, slot_id, "Slot")
    db.delete(slot)
    db.commit()


# ---------------------------------------------------------------------------
# Personalised schedule views
# ---------------------------------------------------------------------------
@router.get(
    "/students/me/schedule",
    response_model=list[SlotOut],
)
def my_student_schedule(
    semester_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return svc.get_student_schedule(
        db, student_id=current.id, semester_id=semester_id,
    )


@router.get(
    "/teachers/me/schedule",
    response_model=list[SlotOut],
)
def my_teacher_schedule(
    semester_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return svc.get_teacher_schedule(
        db, teacher_id=current.id, semester_id=semester_id,
    )


@router.get(
    "/rooms/{room_id}/schedule",
    response_model=list[SlotOut],
)
def room_schedule(
    room_id: str,
    semester_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Room schedules are operationally sensitive (where to find a class) so
    we keep them visible to staff roles only."""
    if current.role not in {
        UserRole.admin, UserRole.manager, UserRole.teacher,
        UserRole.registrar, UserRole.dean,
    }:
        raise PermissionDenied(
            "Room schedules are visible to staff roles only.",
        )
    return svc.get_room_schedule(
        db, room_id=room_id, semester_id=semester_id,
    )
