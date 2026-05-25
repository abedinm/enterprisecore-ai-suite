"""Assignment deadlines + per-student submission state.

Assignment authoring is teacher/admin work; submissions are student-owned.

Workflow features layered on top of the CRUD scaffold:
- ``GET /deadlines/students/me/upcoming`` — upcoming + overdue assignments
  for the current student, with their submission status attached.
- ``POST /deadlines/assignments/{id}/submissions`` — upsert the caller's
  submission (URL, notes, word count) rather than spawning duplicates.
- ``PATCH /deadlines/submissions/{id}/status`` — student walks the status
  state machine: not_started → in_progress → submitted.
- ``GET /deadlines/classes/{class_id}/late-submissions`` — teacher view of
  every submission past its assignment's deadline.

Submission status transition rule: a student may move forward through
not_started → in_progress → submitted, but never back. Teachers/admin can
override via PATCH /submissions/{id}.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.academic._common import (
    TEACHER_OR_ADMIN, _apply_update, _get_or_404, require_any_role,
)
from app.core.exceptions import ConflictError, NotFoundError
from app.db.session import get_db
from app.models.academic.deadlines import (
    AcademicAssignment, AcademicAssignmentSubmission,
)
from app.models.user import User, UserRole
from app.schemas.academic.deadlines import (
    AssignmentCreate, AssignmentOut, AssignmentUpdate, StudentSubmissionUpsert,
    SubmissionCreate, SubmissionOut, SubmissionStatusPatch, SubmissionUpdate,
    UpcomingAssignmentOut,
)

router = APIRouter()


# Forward-only status state machine for student-driven transitions.
_STATUS_ORDER: dict[str, int] = {
    "not_started": 0, "in_progress": 1, "submitted": 2, "late": 2,
}


def _is_staff(role) -> bool:
    return role in {
        UserRole.admin, UserRole.manager, UserRole.teacher,
    }


def _aware(dt: datetime | None) -> datetime | None:
    """Treat naive datetimes coming back from SQLite as UTC.

    SQLite's ``DateTime`` column type drops the tzinfo on read even when we
    wrote it with one. Normalising here lets the workflow code do ``a < b``
    without TypeError when comparing aware "now" against the row's stored
    deadline.
    """
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Student dashboard view
# ---------------------------------------------------------------------------
@router.get(
    "/students/me/upcoming",
    response_model=list[UpcomingAssignmentOut],
)
def my_upcoming_deadlines(
    days: int = 14,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Assignments with deadlines in the next N days, plus any overdue ones
    the student hasn't submitted yet. Sorted by deadline ascending."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=max(1, min(days, 90)))
    # Pull every assignment in window OR any that are still pending past due.
    rows = db.scalars(
        select(AcademicAssignment)
        .where(AcademicAssignment.deadline <= cutoff)
        .order_by(AcademicAssignment.deadline)
    ).all()
    if not rows:
        return []
    # Fetch this student's submissions for those assignments in one query.
    submission_map = {
        s.assignment_id: s for s in db.scalars(
            select(AcademicAssignmentSubmission).where(
                AcademicAssignmentSubmission.student_id == current.id,
                AcademicAssignmentSubmission.assignment_id.in_(
                    [r.id for r in rows]
                ),
            )
        ).all()
    }
    out: list[UpcomingAssignmentOut] = []
    for r in rows:
        sub = submission_map.get(r.id)
        is_overdue = (_aware(r.deadline) or now) < now
        sub_status = sub.status if sub else "not_started"
        # Skip past-due assignments the student has already submitted —
        # they're not actionable on a dashboard.
        if is_overdue and sub_status in {"submitted", "late"}:
            continue
        out.append(UpcomingAssignmentOut(
            assignment=AssignmentOut.model_validate(r),
            is_overdue=is_overdue,
            submission_status=sub_status,
        ))
    return out


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------
@router.get("/assignments", response_model=list[AssignmentOut])
def list_assignments(
    class_id: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(AcademicAssignment).order_by(AcademicAssignment.deadline)
    if class_id:
        stmt = stmt.where(AcademicAssignment.class_id == class_id)
    return db.scalars(stmt).all()


@router.post(
    "/assignments",
    response_model=AssignmentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*TEACHER_OR_ADMIN))],
)
def create_assignment(payload: AssignmentCreate, db: Session = Depends(get_db)):
    obj = AcademicAssignment(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/assignments/{assignment_id}", response_model=AssignmentOut)
def get_assignment(assignment_id: str, db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    return _get_or_404(db, AcademicAssignment, assignment_id, "Assignment")


@router.post(
    "/assignments/{assignment_id}/submissions",
    response_model=SubmissionOut,
)
def upsert_my_submission(
    assignment_id: str,
    payload: StudentSubmissionUpsert,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Create or update the caller's submission for one assignment.

    Idempotent — repeated POSTs reuse the same submission row (matched by the
    unique ``(assignment_id, student_id)`` constraint) so this can stand in
    for both "first submit" and "update my work".
    """
    assignment = _get_or_404(
        db, AcademicAssignment, assignment_id, "Assignment",
    )
    sub = db.scalar(
        select(AcademicAssignmentSubmission).where(
            AcademicAssignmentSubmission.assignment_id == assignment.id,
            AcademicAssignmentSubmission.student_id == current.id,
        )
    )
    # Infer a sensible default status: if the student supplied a URL we move
    # them to "submitted" (or "late" past deadline), otherwise leave the
    # status alone (or set to in_progress for a new row).
    explicit_status = payload.status
    if explicit_status is None:
        if payload.submission_url.strip():
            now_utc = datetime.now(timezone.utc)
            deadline = _aware(assignment.deadline) or now_utc
            explicit_status = (
                "late" if deadline < now_utc else "submitted"
            )
        else:
            explicit_status = "in_progress"
    if sub is None:
        sub = AcademicAssignmentSubmission(
            assignment_id=assignment.id,
            student_id=current.id,
            status=explicit_status,
            word_count=payload.word_count,
            submission_url=payload.submission_url,
            notes=payload.notes,
        )
        db.add(sub)
    else:
        sub.status = explicit_status
        sub.word_count = payload.word_count
        sub.submission_url = payload.submission_url
        sub.notes = payload.notes
    db.commit()
    db.refresh(sub)
    return sub


@router.patch(
    "/assignments/{assignment_id}",
    response_model=AssignmentOut,
    dependencies=[Depends(require_any_role(*TEACHER_OR_ADMIN))],
)
def update_assignment(
    assignment_id: str, payload: AssignmentUpdate,
    db: Session = Depends(get_db),
):
    obj = _get_or_404(db, AcademicAssignment, assignment_id, "Assignment")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*TEACHER_OR_ADMIN))],
)
def delete_assignment(assignment_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, AcademicAssignment, assignment_id, "Assignment")
    db.delete(obj)
    db.commit()


# ---------------------------------------------------------------------------
# Teacher view: every late submission in a class
# ---------------------------------------------------------------------------
@router.get(
    "/classes/{class_id}/late-submissions",
    response_model=list[SubmissionOut],
    dependencies=[Depends(require_any_role(*TEACHER_OR_ADMIN))],
)
def late_submissions_for_class(
    class_id: str,
    db: Session = Depends(get_db),
):
    """Return every submission in a class that's past its deadline.

    A submission counts as late if (a) the submitted_at is after the
    assignment deadline, or (b) the assignment deadline has passed and the
    submission is still in flight (in_progress / not_started).
    """
    now = datetime.now(timezone.utc)
    assignments = db.scalars(
        select(AcademicAssignment).where(
            AcademicAssignment.class_id == class_id,
        )
    ).all()
    if not assignments:
        return []
    deadline_by_id = {a.id: a.deadline for a in assignments}
    submissions = db.scalars(
        select(AcademicAssignmentSubmission)
        .where(
            AcademicAssignmentSubmission.assignment_id.in_(
                list(deadline_by_id),
            )
        )
        .order_by(AcademicAssignmentSubmission.submitted_at.desc())
    ).all()
    out = []
    for s in submissions:
        deadline = _aware(deadline_by_id.get(s.assignment_id))
        if deadline is None:
            continue
        submitted_at = _aware(s.submitted_at)
        late_by_time = submitted_at is not None and submitted_at > deadline
        late_by_status = (
            deadline < now and s.status in {"not_started", "in_progress"}
        )
        if late_by_time or late_by_status:
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# Submissions (catch-all CRUD kept compatible with existing tests)
# ---------------------------------------------------------------------------
@router.get("/submissions", response_model=list[SubmissionOut])
def list_submissions(
    assignment_id: str | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    stmt = select(AcademicAssignmentSubmission).order_by(
        AcademicAssignmentSubmission.submitted_at.desc()
    )
    if not _is_staff(current.role):
        stmt = stmt.where(AcademicAssignmentSubmission.student_id == current.id)
    if assignment_id:
        stmt = stmt.where(
            AcademicAssignmentSubmission.assignment_id == assignment_id
        )
    return db.scalars(stmt).all()


@router.post(
    "/submissions",
    response_model=SubmissionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_submission(
    payload: SubmissionCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = AcademicAssignmentSubmission(
        student_id=current.id, **payload.model_dump()
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/submissions/{submission_id}", response_model=SubmissionOut)
def get_submission(
    submission_id: str, db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = _get_or_404(
        db, AcademicAssignmentSubmission, submission_id, "Submission",
    )
    if obj.student_id != current.id and not _is_staff(current.role):
        raise NotFoundError("Submission not found")
    return obj


@router.patch(
    "/submissions/{submission_id}/status",
    response_model=SubmissionOut,
)
def transition_submission_status(
    submission_id: str,
    payload: SubmissionStatusPatch,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Student-driven forward-only status transition.

    Staff (teacher/admin) can use the generic PATCH /submissions/{id}
    endpoint to override status arbitrarily; this one is the safe path the
    student UI uses ("mark as started", "mark as submitted").
    """
    obj = _get_or_404(
        db, AcademicAssignmentSubmission, submission_id, "Submission",
    )
    if obj.student_id != current.id and not _is_staff(current.role):
        raise NotFoundError("Submission not found")
    new_status = payload.status
    if not _is_staff(current.role):
        old_rank = _STATUS_ORDER.get(obj.status or "not_started", -1)
        new_rank = _STATUS_ORDER.get(new_status, -1)
        if new_rank < old_rank:
            raise ConflictError(
                f"Cannot move submission from '{obj.status}' back to "
                f"'{new_status}'. Ask a teacher to override.",
            )
    obj.status = new_status
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/submissions/{submission_id}", response_model=SubmissionOut)
def update_submission(
    submission_id: str, payload: SubmissionUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = _get_or_404(
        db, AcademicAssignmentSubmission, submission_id, "Submission",
    )
    if obj.student_id != current.id and not _is_staff(current.role):
        raise NotFoundError("Submission not found")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/submissions/{submission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_submission(
    submission_id: str, db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = _get_or_404(
        db, AcademicAssignmentSubmission, submission_id, "Submission",
    )
    if obj.student_id != current.id and not _is_staff(current.role):
        raise NotFoundError("Submission not found")
    db.delete(obj)
    db.commit()
