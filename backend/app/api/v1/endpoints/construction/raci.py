"""RACI matrix CRUD."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.construction._common import (
    PM_ROLES, _apply_update, _get_or_404, get_project_or_404, require_any_role,
)
from app.db.session import get_db
from app.models.construction.raci import ConstructionRaciEntry
from app.models.user import User
from app.schemas.construction.raci import (
    RaciEntryCreate, RaciEntryOut, RaciEntryUpdate,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/raci", response_model=list[RaciEntryOut],
)
def list_raci(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return db.scalars(
        select(ConstructionRaciEntry)
        .where(ConstructionRaciEntry.construction_project_id == project_id)
        .order_by(ConstructionRaciEntry.activity.asc())
    ).all()


@router.post(
    "/projects/{project_id}/raci",
    response_model=RaciEntryOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def create_raci(
    project_id: str,
    payload: RaciEntryCreate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = ConstructionRaciEntry(
        construction_project_id=project_id, **payload.model_dump(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get(
    "/projects/{project_id}/raci/{entry_id}",
    response_model=RaciEntryOut,
)
def get_raci(
    project_id: str,
    entry_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return _get_or_404(db, ConstructionRaciEntry, entry_id, "RACI entry")


@router.patch(
    "/projects/{project_id}/raci/{entry_id}",
    response_model=RaciEntryOut,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def update_raci(
    project_id: str,
    entry_id: str,
    payload: RaciEntryUpdate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionRaciEntry, entry_id, "RACI entry")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/projects/{project_id}/raci/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def delete_raci(
    project_id: str,
    entry_id: str,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionRaciEntry, entry_id, "RACI entry")
    db.delete(obj)
    db.commit()
