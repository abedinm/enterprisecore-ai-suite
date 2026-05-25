"""Study group matching — student-owned profiles + computed matches.

Matching is intentionally simple here: the endpoint computes match scores on
demand against other public profiles. Production deployment may want this as
a background job; that's out of scope for the academic scaffold.

Workflow features layered on top of the CRUD scaffold:
- ``POST /study-match/profiles/me/refresh-matches`` — re-runs the scorer for
  the signed-in student and writes fresh rows (named alias of the existing
  GET /matches endpoint with no-side-effect semantics flipped to POST).
- ``GET /study-match/profiles/me/top-matches`` — top-N matches with profile
  previews (name, department, semester, shared course codes).
- ``POST /study-match/matches/{match_id}/connect`` — fires a Notification at
  the other student via the existing in-app inbox.
- ``POST /study-match/profiles/me/courses`` — replaces the student's course
  list and re-runs the scorer in one round-trip.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.academic._common import _apply_update, _get_or_404
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.academic.study_match import (
    AcademicStudyGroupMatch, AcademicStudyProfile,
)
from app.models.user import Notification, User
from app.schemas.academic.study_match import (
    ConnectOut, CoursesUpdateIn, MatchPreview, StudyMatchOut,
    StudyProfileCreate, StudyProfileOut, StudyProfileUpdate,
)

router = APIRouter()


def _score_pair(
    a: AcademicStudyProfile, b: AcademicStudyProfile,
) -> int:
    """Return a 0..100 compatibility score for two profiles.

    Heuristic: shared courses are the strongest signal; matching department /
    semester / preferred time / study style each add a fixed boost.
    """
    shared = set(a.courses or []) & set(b.courses or [])
    score = min(60, len(shared) * 15)
    if a.department and a.department == b.department:
        score += 10
    if a.semester and a.semester == b.semester:
        score += 10
    if a.preferred_time and a.preferred_time == b.preferred_time:
        score += 10
    if a.study_style and a.study_style == b.study_style:
        score += 10
    return max(0, min(100, score))


def _recompute_matches_for(
    db: Session, *, me: AcademicStudyProfile,
) -> list[AcademicStudyGroupMatch]:
    """Idempotently refresh the match rows for one student.

    Existing pair rows are updated in place so the unique constraint
    ``(student_a_id, student_b_id)`` is respected on re-run.
    """
    others = db.scalars(
        select(AcademicStudyProfile).where(
            AcademicStudyProfile.student_id != me.student_id,
            AcademicStudyProfile.is_public.is_(True),
        )
    ).all()
    existing = {
        (m.student_a_id, m.student_b_id): m
        for m in db.scalars(
            select(AcademicStudyGroupMatch).where(
                (AcademicStudyGroupMatch.student_a_id == me.student_id)
                | (AcademicStudyGroupMatch.student_b_id == me.student_id)
            )
        ).all()
    }
    out: list[AcademicStudyGroupMatch] = []
    for other in others:
        score = _score_pair(me, other)
        a_id, b_id = sorted([me.student_id, other.student_id])
        row = existing.get((a_id, b_id))
        if row is None:
            row = AcademicStudyGroupMatch(
                student_a_id=a_id, student_b_id=b_id, score=score,
            )
            db.add(row)
        else:
            row.score = score
        out.append(row)
    db.commit()
    for row in out:
        db.refresh(row)
    out.sort(key=lambda r: r.score, reverse=True)
    return out


def _my_profile_or_404(db: Session, current: User) -> AcademicStudyProfile:
    obj = db.scalar(
        select(AcademicStudyProfile)
        .where(AcademicStudyProfile.student_id == current.id)
    )
    if obj is None:
        raise NotFoundError("Profile not found")
    return obj


@router.get("/profile/me", response_model=StudyProfileOut)
def get_my_profile(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return _my_profile_or_404(db, current)


@router.post(
    "/profile",
    response_model=StudyProfileOut,
    status_code=status.HTTP_201_CREATED,
)
def upsert_my_profile(
    payload: StudyProfileCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """POST is upsert here — a student has at most one profile, so creating
    "another" is really an update."""
    obj = db.scalar(
        select(AcademicStudyProfile)
        .where(AcademicStudyProfile.student_id == current.id)
    )
    if obj is None:
        obj = AcademicStudyProfile(student_id=current.id, **payload.model_dump())
        db.add(obj)
    else:
        for key, value in payload.model_dump().items():
            setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/profile/me", response_model=StudyProfileOut)
def update_my_profile(
    payload: StudyProfileUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = _my_profile_or_404(db, current)
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/profile/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_profile(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = _my_profile_or_404(db, current)
    db.delete(obj)
    db.commit()


# ---------------------------------------------------------------------------
# Course list management — replaces the list and re-runs the scorer.
# ---------------------------------------------------------------------------
@router.post(
    "/profiles/me/courses",
    response_model=StudyProfileOut,
)
def update_my_courses(
    payload: CoursesUpdateIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Replace the student's course list with the provided one and refresh
    every match row for that student in the same commit."""
    obj = _my_profile_or_404(db, current)
    obj.courses = list(payload.courses)
    db.commit()
    db.refresh(obj)
    _recompute_matches_for(db, me=obj)
    return obj


# ---------------------------------------------------------------------------
# Match views + actions
# ---------------------------------------------------------------------------
@router.post(
    "/profiles/me/refresh-matches",
    response_model=list[StudyMatchOut],
)
def refresh_my_matches(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Re-run the scorer for the signed-in student. Idempotent."""
    me = _my_profile_or_404(db, current)
    return _recompute_matches_for(db, me=me)


@router.get(
    "/profiles/me/top-matches",
    response_model=list[MatchPreview],
)
def my_top_matches(
    limit: int = 10,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Top-N matches enriched with a profile preview for the UI.

    Returns an empty list when the caller has no profile yet — the UI then
    nudges them to create one rather than showing a confusing 404.
    """
    me = db.scalar(
        select(AcademicStudyProfile)
        .where(AcademicStudyProfile.student_id == current.id)
    )
    if me is None:
        return []
    matches = db.scalars(
        select(AcademicStudyGroupMatch)
        .where(
            (AcademicStudyGroupMatch.student_a_id == current.id)
            | (AcademicStudyGroupMatch.student_b_id == current.id)
        )
        .order_by(AcademicStudyGroupMatch.score.desc())
        .limit(max(1, min(limit, 50)))
    ).all()
    if not matches:
        return []
    other_ids = {
        (m.student_b_id if m.student_a_id == current.id else m.student_a_id)
        for m in matches
    }
    # Pull profiles + users in two batches to avoid per-row queries.
    profiles_by_student = {
        p.student_id: p for p in db.scalars(
            select(AcademicStudyProfile).where(
                AcademicStudyProfile.student_id.in_(other_ids),
            )
        ).all()
    }
    users_by_id = {
        u.id: u for u in db.scalars(
            select(User).where(User.id.in_(other_ids))
        ).all()
    }
    out: list[MatchPreview] = []
    my_courses = set(me.courses or [])
    for m in matches:
        other_id = (
            m.student_b_id if m.student_a_id == current.id else m.student_a_id
        )
        prof = profiles_by_student.get(other_id)
        user = users_by_id.get(other_id)
        shared = sorted(
            list(my_courses & set(prof.courses or [])) if prof else []
        )
        out.append(MatchPreview(
            match_id=m.id,
            score=m.score,
            student_id=other_id,
            full_name=(user.full_name if user else other_id),
            department=(prof.department if prof else ""),
            semester=(prof.semester if prof else ""),
            shared_courses=shared,
        ))
    return out


@router.post(
    "/matches/{match_id}/connect",
    response_model=ConnectOut,
    status_code=status.HTTP_201_CREATED,
)
def connect_to_match(
    match_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Fire a Notification at the other student in the match.

    Uses the existing in-app inbox model — no email, no SMS. The other
    student sees the request next time they refresh their notifications
    panel and can act on it from there.
    """
    match = _get_or_404(db, AcademicStudyGroupMatch, match_id, "Match")
    if current.id not in {match.student_a_id, match.student_b_id}:
        raise NotFoundError("Match not found")
    other_id = (
        match.student_b_id if match.student_a_id == current.id
        else match.student_a_id
    )
    notif = Notification(
        user_id=other_id,
        title=f"Study buddy request from {current.full_name}",
        body=(
            f"{current.full_name} would like to study together "
            f"(match score {match.score}/100)."
        ),
        level="info",
        link="/academic/study-buddies",
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return ConnectOut(
        notification_id=notif.id, other_student_id=other_id,
    )


@router.get("/matches", response_model=list[StudyMatchOut])
def list_matches(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Compute matches for the current student against every other public
    profile and persist them. Idempotent — re-running just refreshes scores.
    """
    me = db.scalar(
        select(AcademicStudyProfile)
        .where(AcademicStudyProfile.student_id == current.id)
    )
    if me is None:
        return []
    return _recompute_matches_for(db, me=me)
