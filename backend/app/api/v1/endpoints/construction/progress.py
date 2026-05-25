"""Progress reports — daily/weekly submissions from site."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.construction._common import (
    PM_ROLES, _apply_update, _get_or_404, get_project_or_404, require_any_role,
)
from app.db.session import get_db
from app.models.construction.progress import ConstructionProgressReport
from app.models.user import User
from app.schemas.construction.progress import (
    ProgressReportCreate, ProgressReportOut, ProgressReportUpdate,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/progress-reports",
    response_model=list[ProgressReportOut],
)
def list_reports(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return db.scalars(
        select(ConstructionProgressReport)
        .where(ConstructionProgressReport.construction_project_id == project_id)
        .order_by(ConstructionProgressReport.report_date.desc())
    ).all()


@router.post(
    "/projects/{project_id}/progress-reports",
    response_model=ProgressReportOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def create_report(
    project_id: str,
    payload: ProgressReportCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_any_role(*PM_ROLES)),
):
    get_project_or_404(db, project_id)
    obj = ConstructionProgressReport(
        construction_project_id=project_id,
        reported_by_id=current.id,
        **payload.model_dump(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get(
    "/projects/{project_id}/progress-reports/{report_id}",
    response_model=ProgressReportOut,
)
def get_report(
    project_id: str,
    report_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return _get_or_404(
        db, ConstructionProgressReport, report_id, "Progress report",
    )


@router.patch(
    "/projects/{project_id}/progress-reports/{report_id}",
    response_model=ProgressReportOut,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def update_report(
    project_id: str,
    report_id: str,
    payload: ProgressReportUpdate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(
        db, ConstructionProgressReport, report_id, "Progress report",
    )
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/projects/{project_id}/progress-reports/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def delete_report(
    project_id: str,
    report_id: str,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(
        db, ConstructionProgressReport, report_id, "Progress report",
    )
    db.delete(obj)
    db.commit()
