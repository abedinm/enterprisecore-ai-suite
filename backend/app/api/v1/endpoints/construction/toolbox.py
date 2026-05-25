"""Toolbox talk CRUD — daily safety briefings."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.construction._common import (
    PM_ROLES, _apply_update, _get_or_404, get_project_or_404, require_any_role,
)
from app.db.session import get_db
from app.models.construction.toolbox import ConstructionToolboxTalk
from app.models.user import User
from app.schemas.construction.toolbox import (
    ToolboxTalkCreate, ToolboxTalkOut, ToolboxTalkUpdate,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/toolbox-talks",
    response_model=list[ToolboxTalkOut],
)
def list_talks(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return db.scalars(
        select(ConstructionToolboxTalk)
        .where(ConstructionToolboxTalk.construction_project_id == project_id)
        .order_by(ConstructionToolboxTalk.conducted_at.desc().nullslast())
    ).all()


@router.post(
    "/projects/{project_id}/toolbox-talks",
    response_model=ToolboxTalkOut,
    status_code=status.HTTP_201_CREATED,
)
def create_talk(
    project_id: str,
    payload: ToolboxTalkCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_any_role(*PM_ROLES)),
):
    get_project_or_404(db, project_id)
    obj = ConstructionToolboxTalk(
        construction_project_id=project_id,
        conducted_by_id=current.id,
        **payload.model_dump(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get(
    "/projects/{project_id}/toolbox-talks/{talk_id}",
    response_model=ToolboxTalkOut,
)
def get_talk(
    project_id: str,
    talk_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return _get_or_404(db, ConstructionToolboxTalk, talk_id, "Toolbox talk")


@router.patch(
    "/projects/{project_id}/toolbox-talks/{talk_id}",
    response_model=ToolboxTalkOut,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def update_talk(
    project_id: str,
    talk_id: str,
    payload: ToolboxTalkUpdate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionToolboxTalk, talk_id, "Toolbox talk")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/projects/{project_id}/toolbox-talks/{talk_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def delete_talk(
    project_id: str,
    talk_id: str,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionToolboxTalk, talk_id, "Toolbox talk")
    db.delete(obj)
    db.commit()
