"""Site instruction CRUD with auto-numbering (SI-NNN per project)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.construction._common import (
    PM_ROLES, _apply_update, _get_or_404, get_project_or_404, require_any_role,
)
from app.db.session import get_db
from app.models.construction.site_instructions import ConstructionSiteInstruction
from app.models.user import User
from app.schemas.construction.site_instructions import (
    SiteInstructionCreate, SiteInstructionOut, SiteInstructionUpdate,
)
from app.services.construction import next_si_number

router = APIRouter()


@router.get(
    "/projects/{project_id}/site-instructions",
    response_model=list[SiteInstructionOut],
)
def list_sis(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return db.scalars(
        select(ConstructionSiteInstruction)
        .where(ConstructionSiteInstruction.construction_project_id == project_id)
        .order_by(ConstructionSiteInstruction.created_at.desc())
    ).all()


@router.post(
    "/projects/{project_id}/site-instructions",
    response_model=SiteInstructionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_si(
    project_id: str,
    payload: SiteInstructionCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_any_role(*PM_ROLES)),
):
    get_project_or_404(db, project_id)
    # next_si_number reads from the same session under the same row-lock as
    # the insert, so two concurrent writers in the same DB transaction will
    # still get distinct numbers (and the unique constraint catches the rare
    # truly-racing case across separate sessions).
    number = next_si_number(db, project_id)
    obj = ConstructionSiteInstruction(
        construction_project_id=project_id,
        number=number,
        issued_by_id=current.id,
        **payload.model_dump(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get(
    "/projects/{project_id}/site-instructions/{si_id}",
    response_model=SiteInstructionOut,
)
def get_si(
    project_id: str,
    si_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return _get_or_404(db, ConstructionSiteInstruction, si_id, "Site instruction")


@router.patch(
    "/projects/{project_id}/site-instructions/{si_id}",
    response_model=SiteInstructionOut,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def update_si(
    project_id: str,
    si_id: str,
    payload: SiteInstructionUpdate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionSiteInstruction, si_id, "Site instruction")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/projects/{project_id}/site-instructions/{si_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def delete_si(
    project_id: str,
    si_id: str,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionSiteInstruction, si_id, "Site instruction")
    db.delete(obj)
    db.commit()
