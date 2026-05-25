"""Construction project CRUD + the dashboard rollup endpoint.

Routes here sit at the package root (``/api/v1/construction/projects``).
Per-project sub-resources (risks, milestones, etc.) live in their own
sub-routers but are mounted under this same prefix so the URL space stays
consistent (e.g. ``/projects/{id}/risks``).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.construction._common import (
    PM_ROLES, _apply_update, _get_or_404, require_any_role,
)
from app.db.session import get_db
from app.models.construction.projects import ConstructionProject
from app.models.user import User
from app.schemas.construction.dashboard import DashboardOut
from app.schemas.construction.projects import (
    ConstructionProjectCreate, ConstructionProjectOut,
    ConstructionProjectUpdate,
)
from app.services import construction as svc
from app.services.event_bus import publish_event

router = APIRouter()


@router.get("/projects", response_model=list[ConstructionProjectOut])
def list_projects(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(ConstructionProject).order_by(
        ConstructionProject.created_at.desc()
    )
    if status_filter:
        stmt = stmt.where(ConstructionProject.status == status_filter)
    return db.scalars(stmt).all()


@router.post(
    "/projects",
    response_model=ConstructionProjectOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def create_project(
    payload: ConstructionProjectCreate, db: Session = Depends(get_db),
):
    obj = ConstructionProject(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    publish_event(
        "construction.project.created",
        payload={"project_id": obj.id, "name": obj.name},
    )
    return obj


@router.get("/projects/{project_id}", response_model=ConstructionProjectOut)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return _get_or_404(db, ConstructionProject, project_id, "Construction project")


@router.patch(
    "/projects/{project_id}",
    response_model=ConstructionProjectOut,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def update_project(
    project_id: str,
    payload: ConstructionProjectUpdate,
    db: Session = Depends(get_db),
):
    obj = _get_or_404(db, ConstructionProject, project_id, "Construction project")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, ConstructionProject, project_id, "Construction project")
    db.delete(obj)
    db.commit()


@router.get(
    "/projects/{project_id}/dashboard",
    response_model=DashboardOut,
)
def project_dashboard(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Single rollup the construction dashboard consumes on mount."""
    return svc.dashboard_summary(db, project_id)
