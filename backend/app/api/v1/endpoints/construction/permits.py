"""Permit CRUD (building, planning, environmental, etc.)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.construction._common import (
    PM_ROLES, _apply_update, _get_or_404, get_project_or_404, require_any_role,
)
from app.db.session import get_db
from app.models.construction.permits import ConstructionPermit
from app.models.user import User
from app.schemas.construction.permits import (
    PermitCreate, PermitOut, PermitUpdate,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/permits", response_model=list[PermitOut],
)
def list_permits(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return db.scalars(
        select(ConstructionPermit)
        .where(ConstructionPermit.construction_project_id == project_id)
        .order_by(ConstructionPermit.created_at.desc())
    ).all()


@router.post(
    "/projects/{project_id}/permits",
    response_model=PermitOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def create_permit(
    project_id: str,
    payload: PermitCreate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = ConstructionPermit(
        construction_project_id=project_id, **payload.model_dump(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get(
    "/projects/{project_id}/permits/{permit_id}", response_model=PermitOut,
)
def get_permit(
    project_id: str,
    permit_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return _get_or_404(db, ConstructionPermit, permit_id, "Permit")


@router.patch(
    "/projects/{project_id}/permits/{permit_id}",
    response_model=PermitOut,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def update_permit(
    project_id: str,
    permit_id: str,
    payload: PermitUpdate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionPermit, permit_id, "Permit")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/projects/{project_id}/permits/{permit_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def delete_permit(
    project_id: str,
    permit_id: str,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionPermit, permit_id, "Permit")
    db.delete(obj)
    db.commit()
