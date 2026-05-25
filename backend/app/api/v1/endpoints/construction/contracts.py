"""Construction contract CRUD."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.construction._common import (
    PM_ROLES, _apply_update, _get_or_404, get_project_or_404, require_any_role,
)
from app.db.session import get_db
from app.models.construction.contracts import ConstructionContract
from app.models.user import User
from app.schemas.construction.contracts import (
    ContractCreate, ContractOut, ContractUpdate,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/contracts", response_model=list[ContractOut],
)
def list_contracts(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return db.scalars(
        select(ConstructionContract)
        .where(ConstructionContract.construction_project_id == project_id)
        .order_by(ConstructionContract.created_at.desc())
    ).all()


@router.post(
    "/projects/{project_id}/contracts",
    response_model=ContractOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def create_contract(
    project_id: str,
    payload: ContractCreate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = ConstructionContract(
        construction_project_id=project_id, **payload.model_dump(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get(
    "/projects/{project_id}/contracts/{contract_id}",
    response_model=ContractOut,
)
def get_contract(
    project_id: str,
    contract_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return _get_or_404(db, ConstructionContract, contract_id, "Contract")


@router.patch(
    "/projects/{project_id}/contracts/{contract_id}",
    response_model=ContractOut,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def update_contract(
    project_id: str,
    contract_id: str,
    payload: ContractUpdate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionContract, contract_id, "Contract")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/projects/{project_id}/contracts/{contract_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def delete_contract(
    project_id: str,
    contract_id: str,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionContract, contract_id, "Contract")
    db.delete(obj)
    db.commit()
