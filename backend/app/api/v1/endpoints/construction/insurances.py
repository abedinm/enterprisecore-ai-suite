"""Insurance policy CRUD."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.construction._common import (
    PM_ROLES, _apply_update, _get_or_404, get_project_or_404, require_any_role,
)
from app.db.session import get_db
from app.models.construction.insurances import ConstructionInsurance
from app.models.user import User
from app.schemas.construction.insurances import (
    InsuranceCreate, InsuranceOut, InsuranceUpdate,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/insurances", response_model=list[InsuranceOut],
)
def list_insurances(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return db.scalars(
        select(ConstructionInsurance)
        .where(ConstructionInsurance.construction_project_id == project_id)
        .order_by(ConstructionInsurance.expiry_date.asc().nullslast())
    ).all()


@router.post(
    "/projects/{project_id}/insurances",
    response_model=InsuranceOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def create_insurance(
    project_id: str,
    payload: InsuranceCreate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = ConstructionInsurance(
        construction_project_id=project_id, **payload.model_dump(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get(
    "/projects/{project_id}/insurances/{insurance_id}",
    response_model=InsuranceOut,
)
def get_insurance(
    project_id: str,
    insurance_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return _get_or_404(db, ConstructionInsurance, insurance_id, "Insurance")


@router.patch(
    "/projects/{project_id}/insurances/{insurance_id}",
    response_model=InsuranceOut,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def update_insurance(
    project_id: str,
    insurance_id: str,
    payload: InsuranceUpdate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionInsurance, insurance_id, "Insurance")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/projects/{project_id}/insurances/{insurance_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def delete_insurance(
    project_id: str,
    insurance_id: str,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionInsurance, insurance_id, "Insurance")
    db.delete(obj)
    db.commit()
