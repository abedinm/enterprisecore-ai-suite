"""Timetable — slot scheduling with conflict detection + schedule queries."""
from __future__ import annotations

from datetime import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.models.academic.classes import (
    AcademicClass, AcademicClassEnrollment,
)
from app.models.academic.timetable import AcademicTimetableSlot


def _intervals_overlap(
    a_start: time, a_end: time, b_start: time, b_end: time,
) -> bool:
    """True when two half-open ``[start, end)`` time intervals overlap.

    Time-only comparison (no date) is fine here because slots are scheduled
    within a single calendar day-of-week, not across midnight; cross-midnight
    slots aren't a use-case for the academic timetable.
    """
    return a_start < b_end and b_start < a_end


def _candidate_slots(
    db: Session, *, semester_id: str, day_of_week: int,
    exclude_id: str | None = None,
) -> list[AcademicTimetableSlot]:
    """All slots in the same semester + day, optionally excluding one row.

    We then filter overlaps in Python rather than SQL; the per-semester +
    per-day result set is small (single classroom day worth of slots) so the
    cost is trivial and avoids dialect-specific time-overlap SQL.
    """
    stmt = select(AcademicTimetableSlot).where(
        AcademicTimetableSlot.semester_id == semester_id,
        AcademicTimetableSlot.day_of_week == day_of_week,
    )
    if exclude_id is not None:
        stmt = stmt.where(AcademicTimetableSlot.id != exclude_id)
    return db.scalars(stmt).all()


def _conflict_reason(
    db: Session,
    *,
    class_id: str,
    room_id: str,
    day_of_week: int,
    start_time: time,
    end_time: time,
    semester_id: str,
    exclude_slot_id: str | None = None,
) -> str | None:
    """Return a human-readable reason string if scheduling would conflict,
    else None. The three conflict classes (room, teacher, class) are checked
    in deterministic order so error messages are reproducible across runs.
    """
    candidates = _candidate_slots(
        db, semester_id=semester_id, day_of_week=day_of_week,
        exclude_id=exclude_slot_id,
    )
    if not candidates:
        return None

    # Pre-fetch teacher id for the class we're scheduling so we can compare
    # teacher overlap without N round-trips. Missing class → caller's problem.
    class_row = db.get(AcademicClass, class_id)
    if class_row is None:
        return "class not found"
    teacher_id = class_row.teacher_id

    # Pre-fetch teacher ids of all conflicting candidates in one query.
    cand_class_ids = list({c.class_id for c in candidates})
    teacher_by_class: dict[str, str] = {}
    if cand_class_ids:
        for cls in db.scalars(
            select(AcademicClass).where(AcademicClass.id.in_(cand_class_ids))
        ).all():
            teacher_by_class[cls.id] = cls.teacher_id

    for c in candidates:
        if not _intervals_overlap(start_time, end_time, c.start_time, c.end_time):
            continue
        if c.room_id == room_id:
            return f"room {room_id} is already booked from {c.start_time} to {c.end_time}"
        if teacher_by_class.get(c.class_id) == teacher_id:
            return (
                f"teacher {teacher_id} is already teaching "
                f"from {c.start_time} to {c.end_time}"
            )
        if c.class_id == class_id:
            return (
                f"class {class_id} is already scheduled from "
                f"{c.start_time} to {c.end_time}"
            )
    return None


def schedule_class(
    db: Session,
    *,
    class_id: str,
    room_id: str,
    day_of_week: int,
    start_time: time,
    end_time: time,
    semester_id: str,
) -> AcademicTimetableSlot:
    """Insert a new timetable slot if no conflict, else raise ConflictError."""
    if start_time >= end_time:
        raise ValueError("start_time must be earlier than end_time")
    reason = _conflict_reason(
        db,
        class_id=class_id, room_id=room_id, day_of_week=day_of_week,
        start_time=start_time, end_time=end_time, semester_id=semester_id,
    )
    if reason:
        raise ConflictError(f"Timetable conflict: {reason}")
    slot = AcademicTimetableSlot(
        class_id=class_id, room_id=room_id, day_of_week=day_of_week,
        start_time=start_time, end_time=end_time, semester_id=semester_id,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


def update_slot(
    db: Session, *, slot: AcademicTimetableSlot, payload: dict,
) -> AcademicTimetableSlot:
    """Apply partial updates while re-checking conflicts against the new
    effective shape (so moving a slot to a busy room is rejected)."""
    new_class_id = payload.get("class_id") or slot.class_id
    new_room_id = payload.get("room_id") or slot.room_id
    new_semester_id = payload.get("semester_id") or slot.semester_id
    new_day = payload.get("day_of_week", slot.day_of_week)
    new_start = payload.get("start_time") or slot.start_time
    new_end = payload.get("end_time") or slot.end_time
    if new_start >= new_end:
        raise ValueError("start_time must be earlier than end_time")
    reason = _conflict_reason(
        db,
        class_id=new_class_id, room_id=new_room_id, day_of_week=new_day,
        start_time=new_start, end_time=new_end, semester_id=new_semester_id,
        exclude_slot_id=slot.id,
    )
    if reason:
        raise ConflictError(f"Timetable conflict: {reason}")

    slot.class_id = new_class_id
    slot.room_id = new_room_id
    slot.semester_id = new_semester_id
    slot.day_of_week = new_day
    slot.start_time = new_start
    slot.end_time = new_end
    db.commit()
    db.refresh(slot)
    return slot


def get_room_schedule(
    db: Session, *, room_id: str, semester_id: str,
) -> list[AcademicTimetableSlot]:
    return db.scalars(
        select(AcademicTimetableSlot)
        .where(
            AcademicTimetableSlot.room_id == room_id,
            AcademicTimetableSlot.semester_id == semester_id,
        )
        .order_by(
            AcademicTimetableSlot.day_of_week,
            AcademicTimetableSlot.start_time,
        )
    ).all()


def get_teacher_schedule(
    db: Session, *, teacher_id: str, semester_id: str,
) -> list[AcademicTimetableSlot]:
    """All slots assigned to classes taught by ``teacher_id`` in the semester."""
    class_ids = [
        c.id for c in db.scalars(
            select(AcademicClass).where(
                AcademicClass.teacher_id == teacher_id,
                AcademicClass.semester_id == semester_id,
            )
        ).all()
    ]
    if not class_ids:
        return []
    return db.scalars(
        select(AcademicTimetableSlot)
        .where(
            AcademicTimetableSlot.class_id.in_(class_ids),
            AcademicTimetableSlot.semester_id == semester_id,
        )
        .order_by(
            AcademicTimetableSlot.day_of_week,
            AcademicTimetableSlot.start_time,
        )
    ).all()


def get_student_schedule(
    db: Session, *, student_id: str, semester_id: str,
) -> list[AcademicTimetableSlot]:
    """All slots for classes the student is actively enrolled in this semester."""
    enrolled_class_ids = [
        e.class_id for e in db.scalars(
            select(AcademicClassEnrollment).where(
                AcademicClassEnrollment.student_id == student_id,
                AcademicClassEnrollment.status == "active",
            )
        ).all()
    ]
    if not enrolled_class_ids:
        return []
    return db.scalars(
        select(AcademicTimetableSlot)
        .where(
            AcademicTimetableSlot.class_id.in_(enrolled_class_ids),
            AcademicTimetableSlot.semester_id == semester_id,
        )
        .order_by(
            AcademicTimetableSlot.day_of_week,
            AcademicTimetableSlot.start_time,
        )
    ).all()
