"""Exam scheduling — teacher/registrar/admin write, everyone reads.

Workflow features layered on top of the CRUD scaffold:
- ``POST /exams/{id}/schedule-room`` — assigns a room with double-book
  detection (no two exams in the same room overlapping).
- ``GET /exams/upcoming`` — next N days, for the student dashboard.
- ``GET /exams/by-room/{room_id}`` — registrar room-utilisation report.
- ``GET /exams/calendar`` — exams of a month grouped by date.

Conflict detection uses the same in-Python overlap approach as the
timetable service — the per-day candidate set stays small enough that going
to SQL for the join isn't worth the dialect quirks.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.academic._common import (
    REGISTRAR_OR_ADMIN, _apply_update, _get_or_404, require_any_role,
)
from app.core.exceptions import ConflictError, ValidationFailed
from app.db.session import get_db
from app.models.academic.core import AcademicRoom
from app.models.academic.exams import AcademicExam
from app.models.user import User
from app.schemas.academic.exams import (
    ExamCalendarDay, ExamCreate, ExamOut, ExamScheduleRoomIn, ExamUpdate,
)

router = APIRouter()


def _end_time(start: time, duration_min: int) -> time:
    """Compute end-of-exam time. Caps at 23:59 so we don't roll into the
    next day — academic exams don't span midnight in practice."""
    total_min = start.hour * 60 + start.minute + max(0, duration_min)
    total_min = min(total_min, 23 * 60 + 59)
    return time(hour=total_min // 60, minute=total_min % 60)


def _intervals_overlap(
    a_start: time, a_end: time, b_start: time, b_end: time,
) -> bool:
    return a_start < b_end and b_start < a_end


def _room_conflict(
    db: Session, *, room_id: str, exam_date_: date,
    start_time: time, end_time: time, exclude_exam_id: str | None,
) -> AcademicExam | None:
    """Return the conflicting exam if room is double-booked, else None."""
    stmt = select(AcademicExam).where(
        AcademicExam.room_id == room_id,
        AcademicExam.exam_date == exam_date_,
    )
    if exclude_exam_id:
        stmt = stmt.where(AcademicExam.id != exclude_exam_id)
    for other in db.scalars(stmt).all():
        other_end = _end_time(other.start_time, other.duration_min)
        if _intervals_overlap(start_time, end_time, other.start_time, other_end):
            return other
    return None


# ---------------------------------------------------------------------------
# Workflow / dashboard reads — declared BEFORE /{exam_id} so the dynamic
# path segment doesn't catch them.
# ---------------------------------------------------------------------------
@router.get("/upcoming", response_model=list[ExamOut])
def upcoming_exams(
    days: int = 14,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """All exams in the next ``days`` days (inclusive of today)."""
    today = datetime.now(timezone.utc).date()
    cutoff = today + timedelta(days=max(1, min(days, 365)))
    return db.scalars(
        select(AcademicExam)
        .where(
            AcademicExam.exam_date >= today,
            AcademicExam.exam_date <= cutoff,
        )
        .order_by(AcademicExam.exam_date, AcademicExam.start_time)
    ).all()


@router.get("/by-room/{room_id}", response_model=list[ExamOut])
def exams_by_room(
    room_id: str,
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_role(*REGISTRAR_OR_ADMIN)),
):
    """Registrar room-utilisation: every exam in a room over a window.

    ``from_`` is the query param ``from=`` (reserved keyword in Python; the
    ``alias="from"`` maps the URL name onto the parameter)."""
    stmt = select(AcademicExam).where(AcademicExam.room_id == room_id)
    if from_:
        stmt = stmt.where(AcademicExam.exam_date >= from_)
    if to:
        stmt = stmt.where(AcademicExam.exam_date <= to)
    return db.scalars(
        stmt.order_by(AcademicExam.exam_date, AcademicExam.start_time)
    ).all()


@router.get("/calendar", response_model=list[ExamCalendarDay])
def exam_calendar(
    month: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """All exams in ``YYYY-MM`` grouped by date. Empty days are omitted.

    The frontend usually renders a full month grid, but the API stays terse
    and only ships the dates that actually have exams — the UI fills in the
    gaps.
    """
    try:
        year_s, month_s = month.split("-")
        year = int(year_s)
        month_num = int(month_s)
        first = date(year, month_num, 1)
    except (ValueError, IndexError) as exc:
        raise ValidationFailed(
            "month must be YYYY-MM (e.g. 2026-05)",
        ) from exc
    # First day of next month minus one day = end of this month.
    if month_num == 12:
        next_first = date(year + 1, 1, 1)
    else:
        next_first = date(year, month_num + 1, 1)
    rows = db.scalars(
        select(AcademicExam)
        .where(
            AcademicExam.exam_date >= first,
            AcademicExam.exam_date < next_first,
        )
        .order_by(AcademicExam.exam_date, AcademicExam.start_time)
    ).all()
    grouped: dict[date, list[AcademicExam]] = defaultdict(list)
    for r in rows:
        grouped[r.exam_date].append(r)
    return [
        ExamCalendarDay(exam_date=d, exams=grouped[d])
        for d in sorted(grouped)
    ]


@router.get("/", response_model=list[ExamOut])
def list_exams(
    course_code: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(AcademicExam).order_by(AcademicExam.exam_date)
    if course_code:
        stmt = stmt.where(AcademicExam.course_code == course_code)
    return db.scalars(stmt).all()


@router.post(
    "/",
    response_model=ExamOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def create_exam(payload: ExamCreate, db: Session = Depends(get_db)):
    obj = AcademicExam(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{exam_id}", response_model=ExamOut)
def get_exam(exam_id: str, db: Session = Depends(get_db),
             _: User = Depends(get_current_user)):
    return _get_or_404(db, AcademicExam, exam_id, "Exam")


@router.post(
    "/{exam_id}/schedule-room",
    response_model=ExamOut,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def schedule_room(
    exam_id: str, payload: ExamScheduleRoomIn, db: Session = Depends(get_db),
):
    """Assign or reassign a room for an exam, rejecting double-bookings.

    Two exams in the same room on the same date with overlapping time
    windows are considered a conflict; the response includes the conflicting
    exam id in the message to help the registrar resolve it.
    """
    obj = _get_or_404(db, AcademicExam, exam_id, "Exam")
    # Confirm the room actually exists — better to 404 here than to defer to
    # the FK constraint and get a generic 409 from the integrity handler.
    _get_or_404(db, AcademicRoom, payload.room_id, "Room")
    end_t = _end_time(obj.start_time, obj.duration_min)
    clash = _room_conflict(
        db,
        room_id=payload.room_id,
        exam_date_=obj.exam_date,
        start_time=obj.start_time,
        end_time=end_t,
        exclude_exam_id=obj.id,
    )
    if clash is not None:
        raise ConflictError(
            f"Room {payload.room_id} is already booked by exam {clash.id} "
            f"from {clash.start_time} for {clash.duration_min} min.",
        )
    obj.room_id = payload.room_id
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/{exam_id}",
    response_model=ExamOut,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def update_exam(exam_id: str, payload: ExamUpdate,
                db: Session = Depends(get_db)):
    obj = _get_or_404(db, AcademicExam, exam_id, "Exam")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/{exam_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def delete_exam(exam_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, AcademicExam, exam_id, "Exam")
    db.delete(obj)
    db.commit()
