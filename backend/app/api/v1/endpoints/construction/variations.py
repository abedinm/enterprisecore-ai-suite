"""Variation CRUD with auto-numbering (VAR-NNN per project)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.construction._common import (
    PM_ROLES, _apply_update, _get_or_404, get_project_or_404, require_any_role,
)
from app.db.session import get_db
from app.models.construction.variations import ConstructionVariation
from app.models.user import User
from app.schemas.construction.variations import (
    VariationCreate, VariationOut, VariationUpdate,
)
from app.services.construction import next_variation_number
from app.services.event_bus import publish_event

router = APIRouter()


@router.get(
    "/projects/{project_id}/variations",
    response_model=list[VariationOut],
)
def list_variations(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return db.scalars(
        select(ConstructionVariation)
        .where(ConstructionVariation.construction_project_id == project_id)
        .order_by(ConstructionVariation.created_at.desc())
    ).all()


@router.post(
    "/projects/{project_id}/variations",
    response_model=VariationOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def create_variation(
    project_id: str,
    payload: VariationCreate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    number = next_variation_number(db, project_id)
    obj = ConstructionVariation(
        construction_project_id=project_id,
        number=number,
        **payload.model_dump(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get(
    "/projects/{project_id}/variations/{var_id}",
    response_model=VariationOut,
)
def get_variation(
    project_id: str,
    var_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return _get_or_404(db, ConstructionVariation, var_id, "Variation")


@router.patch(
    "/projects/{project_id}/variations/{var_id}",
    response_model=VariationOut,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def update_variation(
    project_id: str,
    var_id: str,
    payload: VariationUpdate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionVariation, var_id, "Variation")
    previous_status = obj.status
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    if obj.status == "approved" and previous_status != "approved":
        publish_event(
            "construction.variation.approved",
            payload={"variation_id": obj.id, "number": obj.number, "project_id": project_id},
        )
    return obj


@router.delete(
    "/projects/{project_id}/variations/{var_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def delete_variation(
    project_id: str,
    var_id: str,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionVariation, var_id, "Variation")
    db.delete(obj)
    db.commit()
