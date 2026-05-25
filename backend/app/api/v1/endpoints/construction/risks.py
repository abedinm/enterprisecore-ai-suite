"""Risk register CRUD (scoped to a construction project)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.construction._common import (
    PM_ROLES, _apply_update, _get_or_404, get_project_or_404, require_any_role,
)
from app.db.session import get_db
from app.models.construction.risks import ConstructionRisk
from app.models.user import User
from app.schemas.construction.risks import RiskCreate, RiskOut, RiskUpdate
from app.services.construction import compute_risk_score
from app.services.event_bus import publish_event

router = APIRouter()


@router.get("/projects/{project_id}/risks", response_model=list[RiskOut])
def list_risks(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return db.scalars(
        select(ConstructionRisk)
        .where(ConstructionRisk.construction_project_id == project_id)
        .order_by(ConstructionRisk.score.desc(), ConstructionRisk.created_at.desc())
    ).all()


@router.post(
    "/projects/{project_id}/risks",
    response_model=RiskOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def create_risk(
    project_id: str,
    payload: RiskCreate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    data = payload.model_dump()
    score = compute_risk_score(data["probability"], data["impact"])
    obj = ConstructionRisk(
        construction_project_id=project_id, score=score, **data,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    publish_event(
        "construction.risk.created",
        payload={"risk_id": obj.id, "project_id": project_id, "score": obj.score},
    )
    return obj


@router.get(
    "/projects/{project_id}/risks/{risk_id}", response_model=RiskOut,
)
def get_risk(
    project_id: str,
    risk_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return _get_or_404(db, ConstructionRisk, risk_id, "Risk")


@router.patch(
    "/projects/{project_id}/risks/{risk_id}",
    response_model=RiskOut,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def update_risk(
    project_id: str,
    risk_id: str,
    payload: RiskUpdate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionRisk, risk_id, "Risk")
    data = payload.model_dump(exclude_unset=True)
    _apply_update(obj, data)
    # Re-derive the cached score whenever probability or impact moves.
    if "probability" in data or "impact" in data:
        obj.score = compute_risk_score(obj.probability, obj.impact)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/projects/{project_id}/risks/{risk_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def delete_risk(
    project_id: str,
    risk_id: str,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionRisk, risk_id, "Risk")
    db.delete(obj)
    db.commit()
