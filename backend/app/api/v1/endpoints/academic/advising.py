"""Academic advising sessions — staff schedules + edits; student reads own.

Workflow features layered on top of the CRUD scaffold:
- ``GET /advising/students/{id}/cgpa-trend`` — CGPA points ordered in time so
  the dashboard can render the trend (text or chart, the UI decides).
- ``POST /advising/sessions/{id}/notes`` — appends a stamped + signed line to
  the session's notes field rather than replacing it.
- ``GET /advising/advisors/me/upcoming`` — advisor's next-N-day calendar.
- ``GET /advising/students/me/sessions`` — student's own session history.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.academic._common import (
    REGISTRAR_OR_ADMIN, _apply_update, _get_or_404, require_any_role,
)
from app.core.exceptions import NotFoundError, PermissionDenied
from app.db.session import get_db
from app.models.academic.advising import AcademicAdvisingSession
from app.models.user import User, UserRole
from app.schemas.academic.advising import (
    AdvisingCreate, AdvisingNoteAppend, AdvisingOut, AdvisingUpdate,
    CgpaTrend, CgpaTrendPoint,
)

router = APIRouter()


def _is_staff(role) -> bool:
    return role in {
        UserRole.admin, UserRole.manager, UserRole.teacher,
        UserRole.registrar, UserRole.dean,
    }


@router.get("/sessions", response_model=list[AdvisingOut])
def list_sessions(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    stmt = select(AcademicAdvisingSession).order_by(
        AcademicAdvisingSession.scheduled_at.desc()
    )
    if not _is_staff(current.role):
        # Students only see sessions where they're the student of record.
        stmt = stmt.where(AcademicAdvisingSession.student_id == current.id)
    return db.scalars(stmt).all()


@router.post(
    "/sessions",
    response_model=AdvisingOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def create_session(payload: AdvisingCreate, db: Session = Depends(get_db)):
    obj = AcademicAdvisingSession(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# ---------------------------------------------------------------------------
# Personalised views — declared BEFORE /sessions/{session_id} so the dynamic
# id segment doesn't capture them.
# ---------------------------------------------------------------------------
@router.get(
    "/advisors/me/upcoming",
    response_model=list[AdvisingOut],
)
def my_upcoming_advising(
    days: int = 30,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """The signed-in advisor's upcoming sessions over the next ``days`` days.

    Any authenticated user may call this — non-advisors get an empty list
    because no sessions reference them as ``advisor_id``.
    """
    now = datetime.now(timezone.utc)
    until = now + timedelta(days=max(1, min(days, 365)))
    return db.scalars(
        select(AcademicAdvisingSession)
        .where(
            AcademicAdvisingSession.advisor_id == current.id,
            AcademicAdvisingSession.scheduled_at >= now,
            AcademicAdvisingSession.scheduled_at <= until,
        )
        .order_by(AcademicAdvisingSession.scheduled_at)
    ).all()


@router.get(
    "/students/me/sessions",
    response_model=list[AdvisingOut],
)
def my_student_sessions(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Signed-in student's session history (newest first)."""
    return db.scalars(
        select(AcademicAdvisingSession)
        .where(AcademicAdvisingSession.student_id == current.id)
        .order_by(AcademicAdvisingSession.scheduled_at.desc())
    ).all()


@router.get(
    "/students/{student_id}/cgpa-trend",
    response_model=CgpaTrend,
)
def cgpa_trend(
    student_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """CGPA points across this student's advising history.

    Students can view their own; staff roles can view anyone's. Sessions
    without a ``current_cgpa`` are still included (with ``null``) so the UI
    can show "this session had no CGPA snapshot" rather than silently dropping
    a gap.
    """
    if current.id != student_id and not _is_staff(current.role):
        raise PermissionDenied(
            "You may only view your own CGPA trend unless you have a staff role.",
        )
    rows = db.scalars(
        select(AcademicAdvisingSession)
        .where(AcademicAdvisingSession.student_id == student_id)
        .order_by(AcademicAdvisingSession.scheduled_at)
    ).all()
    points = [
        CgpaTrendPoint(
            scheduled_at=r.scheduled_at, current_cgpa=r.current_cgpa,
        )
        for r in rows
    ]
    return CgpaTrend(student_id=student_id, points=points)


@router.post(
    "/sessions/{session_id}/notes",
    response_model=AdvisingOut,
)
def append_session_notes(
    session_id: str,
    payload: AdvisingNoteAppend,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Append a stamped + signed line to the session notes.

    Format: ``[YYYY-MM-DD HH:MMZ — Full Name] <text>``. The whole field is a
    plain ``Text`` column so this is an append-with-separator, not a row.
    """
    obj = _get_or_404(db, AcademicAdvisingSession, session_id, "Advising session")
    # Staff (the advisor's roles) can always append. Students can append to
    # their own session — the dashboard lets them add a comment after a meeting.
    if not _is_staff(current.role) and obj.student_id != current.id:
        raise NotFoundError("Advising session not found")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    line = f"[{stamp} — {current.full_name}] {payload.text.strip()}"
    obj.notes = (
        f"{obj.notes}\n{line}" if obj.notes else line
    )
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/sessions/{session_id}", response_model=AdvisingOut)
def get_session(
    session_id: str, db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = _get_or_404(db, AcademicAdvisingSession, session_id, "Advising session")
    if obj.student_id != current.id and not _is_staff(current.role):
        raise NotFoundError("Advising session not found")
    return obj


@router.patch(
    "/sessions/{session_id}",
    response_model=AdvisingOut,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def update_session(
    session_id: str, payload: AdvisingUpdate, db: Session = Depends(get_db),
):
    obj = _get_or_404(db, AcademicAdvisingSession, session_id, "Advising session")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*REGISTRAR_OR_ADMIN))],
)
def delete_session(session_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, AcademicAdvisingSession, session_id, "Advising session")
    db.delete(obj)
    db.commit()
