"""Extension of Time CRUD (per construction project)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.construction._common import (
    PM_ROLES, _apply_update, _get_or_404, get_project_or_404, require_any_role,
)
from app.db.session import get_db
from app.models.construction.eot import ConstructionEOTRequest
from app.models.user import User
from app.schemas.construction.eot import (
    EOTRequestCreate, EOTRequestOut, EOTRequestUpdate,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/eot-requests",
    response_model=list[EOTRequestOut],
)
def list_eot(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return db.scalars(
        select(ConstructionEOTRequest)
        .where(ConstructionEOTRequest.construction_project_id == project_id)
        .order_by(ConstructionEOTRequest.created_at.desc())
    ).all()


@router.post(
    "/projects/{project_id}/eot-requests",
    response_model=EOTRequestOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def create_eot(
    project_id: str,
    payload: EOTRequestCreate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = ConstructionEOTRequest(
        construction_project_id=project_id, **payload.model_dump(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get(
    "/projects/{project_id}/eot-requests/{eot_id}",
    response_model=EOTRequestOut,
)
def get_eot(
    project_id: str,
    eot_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return _get_or_404(db, ConstructionEOTRequest, eot_id, "EOT request")


@router.patch(
    "/projects/{project_id}/eot-requests/{eot_id}",
    response_model=EOTRequestOut,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def update_eot(
    project_id: str,
    eot_id: str,
    payload: EOTRequestUpdate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionEOTRequest, eot_id, "EOT request")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/projects/{project_id}/eot-requests/{eot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def delete_eot(
    project_id: str,
    eot_id: str,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionEOTRequest, eot_id, "EOT request")
    db.delete(obj)
    db.commit()
