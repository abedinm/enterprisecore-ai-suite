"""Milestone CRUD (scoped to a construction project)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.construction._common import (
    PM_ROLES, _apply_update, _get_or_404, get_project_or_404, require_any_role,
)
from app.db.session import get_db
from app.models.construction.milestones import ConstructionMilestone
from app.models.user import User
from app.schemas.construction.milestones import (
    MilestoneCreate, MilestoneOut, MilestoneUpdate,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/milestones",
    response_model=list[MilestoneOut],
)
def list_milestones(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return db.scalars(
        select(ConstructionMilestone)
        .where(ConstructionMilestone.construction_project_id == project_id)
        .order_by(ConstructionMilestone.planned_date.asc())
    ).all()


@router.post(
    "/projects/{project_id}/milestones",
    response_model=MilestoneOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def create_milestone(
    project_id: str,
    payload: MilestoneCreate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = ConstructionMilestone(
        construction_project_id=project_id, **payload.model_dump(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get(
    "/projects/{project_id}/milestones/{milestone_id}",
    response_model=MilestoneOut,
)
def get_milestone(
    project_id: str,
    milestone_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return _get_or_404(db, ConstructionMilestone, milestone_id, "Milestone")


@router.patch(
    "/projects/{project_id}/milestones/{milestone_id}",
    response_model=MilestoneOut,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def update_milestone(
    project_id: str,
    milestone_id: str,
    payload: MilestoneUpdate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionMilestone, milestone_id, "Milestone")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/projects/{project_id}/milestones/{milestone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def delete_milestone(
    project_id: str,
    milestone_id: str,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionMilestone, milestone_id, "Milestone")
    db.delete(obj)
    db.commit()
