"""Group projects + per-student assignments.

Workflow features layered on top of the CRUD scaffold:
- ``POST /group/projects/{id}/auto-balance`` — distribute roles + weights
  evenly across a roster, optionally persisting the suggestions when
  ``?commit=true``.
- ``GET /group/projects/{id}/fairness`` — analyse current assignments and
  return a "is this balanced?" verdict + the weight std-dev + improvement
  suggestions.
- ``GET /group/classes/{class_id}/active`` — projects with future deadlines.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.academic._common import (
    TEACHER_OR_ADMIN, _apply_update, _get_or_404, require_any_role,
)
from app.db.session import get_db
from app.models.academic.group_projects import (
    AcademicGroupProject, AcademicGroupProjectAssignment,
)
from app.models.user import User
from app.schemas.academic.group_projects import (
    AutoBalanceIn, AutoBalanceOut, AutoBalanceSuggestion, FairnessOut,
    GroupAssignmentCreate, GroupAssignmentOut, GroupAssignmentUpdate,
    GroupProjectCreate, GroupProjectOut, GroupProjectUpdate,
)

router = APIRouter()


# Fallback role palette when the caller doesn't supply one. Six roles covers
# the typical 3-6 student group; the auto-balance algorithm wraps around for
# larger groups.
_DEFAULT_ROLES = (
    "lead", "researcher", "engineer", "designer", "writer", "qa",
)


# ---------------------------------------------------------------------------
# Projects — workflow reads BEFORE /projects/{project_id}
# ---------------------------------------------------------------------------
@router.get(
    "/classes/{class_id}/active",
    response_model=list[GroupProjectOut],
)
def active_projects_for_class(
    class_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Class roster of projects whose deadline is still in the future."""
    now = datetime.now(timezone.utc)
    return db.scalars(
        select(AcademicGroupProject)
        .where(
            AcademicGroupProject.class_id == class_id,
            AcademicGroupProject.deadline >= now,
        )
        .order_by(AcademicGroupProject.deadline)
    ).all()


@router.get("/projects", response_model=list[GroupProjectOut])
def list_projects(
    class_id: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(AcademicGroupProject).order_by(
        AcademicGroupProject.deadline.desc()
    )
    if class_id:
        stmt = stmt.where(AcademicGroupProject.class_id == class_id)
    return db.scalars(stmt).all()


@router.post(
    "/projects",
    response_model=GroupProjectOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*TEACHER_OR_ADMIN))],
)
def create_project(payload: GroupProjectCreate, db: Session = Depends(get_db)):
    obj = AcademicGroupProject(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/projects/{project_id}", response_model=GroupProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    return _get_or_404(db, AcademicGroupProject, project_id, "Group project")


@router.post(
    "/projects/{project_id}/auto-balance",
    response_model=AutoBalanceOut,
    dependencies=[Depends(require_any_role(*TEACHER_OR_ADMIN))],
)
def auto_balance_project(
    project_id: str,
    payload: AutoBalanceIn,
    commit: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Suggest evenly-distributed roles + weights across the given students.

    Weight is split as 1.00 / N rounded to 2 decimal places with the remainder
    added to the first student so the column total stays at exactly 1.00 —
    avoids the off-by-one cent that would otherwise nag the fairness check.

    When ``commit=true`` we wipe the project's existing assignments and write
    the suggestions in one transaction. Otherwise we just return the proposed
    shape and let the teacher review.
    """
    project = _get_or_404(
        db, AcademicGroupProject, project_id, "Group project",
    )
    roles = list(payload.roles) if payload.roles else list(_DEFAULT_ROLES)
    n = len(payload.student_ids)
    if n == 0:
        return AutoBalanceOut(
            project_id=project.id, suggestions=[], committed=False,
        )
    base = (Decimal("1.00") / Decimal(n)).quantize(Decimal("0.01"))
    suggestions: list[AutoBalanceSuggestion] = []
    running = Decimal("0.00")
    for idx, student_id in enumerate(payload.student_ids):
        if idx == n - 1:
            # Trail-end gets whatever's left so the sum is exactly 1.00.
            weight = (Decimal("1.00") - running).quantize(Decimal("0.01"))
        else:
            weight = base
            running += weight
        suggestions.append(
            AutoBalanceSuggestion(
                student_id=student_id,
                role=roles[idx % len(roles)],
                weight=weight,
            )
        )
    committed = False
    if commit:
        # Wipe existing assignments to avoid mixing old + new in confusing ways.
        for old in db.scalars(
            select(AcademicGroupProjectAssignment).where(
                AcademicGroupProjectAssignment.project_id == project.id,
            )
        ).all():
            db.delete(old)
        for s in suggestions:
            db.add(AcademicGroupProjectAssignment(
                project_id=project.id,
                student_id=s.student_id,
                role=s.role,
                weight=s.weight,
            ))
        db.commit()
        committed = True
    return AutoBalanceOut(
        project_id=project.id, suggestions=suggestions, committed=committed,
    )


@router.get(
    "/projects/{project_id}/fairness",
    response_model=FairnessOut,
)
def project_fairness(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Crude fairness signal: weight std-dev + role coverage.

    "Balanced" is heuristic: weight std-dev < 0.05 (i.e. shares within ~5
    percentage points of each other) AND every assignment has a role.
    """
    project = _get_or_404(
        db, AcademicGroupProject, project_id, "Group project",
    )
    rows = db.scalars(
        select(AcademicGroupProjectAssignment).where(
            AcademicGroupProjectAssignment.project_id == project.id,
        )
    ).all()
    weights = [float(r.weight or 0) for r in rows]
    total = sum(weights)
    std = statistics.pstdev(weights) if len(weights) > 1 else 0.0
    role_coverage = sum(1 for r in rows if r.role and r.role.strip())
    suggestions: list[str] = []
    balanced = True
    if not rows:
        balanced = False
        suggestions.append("No students assigned yet — call /auto-balance.")
    if std > 0.05:
        balanced = False
        suggestions.append(
            "Weights are uneven; run /auto-balance to redistribute.",
        )
    if rows and role_coverage < len(rows):
        balanced = False
        suggestions.append(
            "Some assignments have no role — give every student a named role.",
        )
    if rows and abs(total - 1.0) > 0.05:
        balanced = False
        suggestions.append(
            f"Weights sum to {total:.2f}, expected ~1.00; rebalance.",
        )
    return FairnessOut(
        project_id=project.id,
        balanced=balanced,
        weight_std_dev=round(std, 4),
        weight_total=round(total, 2),
        role_coverage=role_coverage,
        suggestions=suggestions,
    )


@router.patch(
    "/projects/{project_id}",
    response_model=GroupProjectOut,
    dependencies=[Depends(require_any_role(*TEACHER_OR_ADMIN))],
)
def update_project(
    project_id: str, payload: GroupProjectUpdate, db: Session = Depends(get_db),
):
    obj = _get_or_404(db, AcademicGroupProject, project_id, "Group project")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*TEACHER_OR_ADMIN))],
)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, AcademicGroupProject, project_id, "Group project")
    db.delete(obj)
    db.commit()


# ---------------------------------------------------------------------------
# Per-student assignments
# ---------------------------------------------------------------------------
@router.get("/assignments", response_model=list[GroupAssignmentOut])
def list_assignments(
    project_id: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(AcademicGroupProjectAssignment).order_by(
        AcademicGroupProjectAssignment.created_at
    )
    if project_id:
        stmt = stmt.where(AcademicGroupProjectAssignment.project_id == project_id)
    return db.scalars(stmt).all()


@router.post(
    "/assignments",
    response_model=GroupAssignmentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*TEACHER_OR_ADMIN))],
)
def create_assignment(
    payload: GroupAssignmentCreate, db: Session = Depends(get_db),
):
    obj = AcademicGroupProjectAssignment(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/assignments/{assignment_id}",
    response_model=GroupAssignmentOut,
    dependencies=[Depends(require_any_role(*TEACHER_OR_ADMIN))],
)
def update_assignment(
    assignment_id: str, payload: GroupAssignmentUpdate,
    db: Session = Depends(get_db),
):
    obj = _get_or_404(
        db, AcademicGroupProjectAssignment, assignment_id, "Assignment",
    )
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
    obj = _get_or_404(
        db, AcademicGroupProjectAssignment, assignment_id, "Assignment",
    )
    db.delete(obj)
    db.commit()
