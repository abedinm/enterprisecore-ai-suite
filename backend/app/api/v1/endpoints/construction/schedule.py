"""Schedule tasks + Gantt dependencies (per construction project)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.construction._common import (
    PM_ROLES, _apply_update, _get_or_404, get_project_or_404, require_any_role,
)
from app.db.session import get_db
from app.models.construction.schedule import (
    ConstructionScheduleDependency, ConstructionScheduleTask,
)
from app.models.user import User
from app.schemas.construction.schedule import (
    ScheduleDependencyCreate, ScheduleDependencyOut, ScheduleDependencyUpdate,
    ScheduleTaskCreate, ScheduleTaskOut, ScheduleTaskUpdate,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
@router.get(
    "/projects/{project_id}/schedule/tasks",
    response_model=list[ScheduleTaskOut],
)
def list_tasks(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return db.scalars(
        select(ConstructionScheduleTask)
        .where(ConstructionScheduleTask.construction_project_id == project_id)
        .order_by(
            ConstructionScheduleTask.start_date.asc().nullslast(),
            ConstructionScheduleTask.created_at.asc(),
        )
    ).all()


@router.post(
    "/projects/{project_id}/schedule/tasks",
    response_model=ScheduleTaskOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def create_task(
    project_id: str,
    payload: ScheduleTaskCreate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = ConstructionScheduleTask(
        construction_project_id=project_id, **payload.model_dump(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get(
    "/projects/{project_id}/schedule/tasks/{task_id}",
    response_model=ScheduleTaskOut,
)
def get_task(
    project_id: str,
    task_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return _get_or_404(db, ConstructionScheduleTask, task_id, "Schedule task")


@router.patch(
    "/projects/{project_id}/schedule/tasks/{task_id}",
    response_model=ScheduleTaskOut,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def update_task(
    project_id: str,
    task_id: str,
    payload: ScheduleTaskUpdate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionScheduleTask, task_id, "Schedule task")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/projects/{project_id}/schedule/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def delete_task(
    project_id: str,
    task_id: str,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(db, ConstructionScheduleTask, task_id, "Schedule task")
    db.delete(obj)
    db.commit()


# ---------------------------------------------------------------------------
# Dependencies (Gantt edges)
# ---------------------------------------------------------------------------
@router.get(
    "/projects/{project_id}/schedule/dependencies",
    response_model=list[ScheduleDependencyOut],
)
def list_dependencies(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Edges whose predecessor task lives on this project.

    The successor *should* live on the same project — the API contract trusts
    the caller for that today; future tightening would add a CHECK.
    """
    get_project_or_404(db, project_id)
    task_ids = {
        t.id for t in db.scalars(
            select(ConstructionScheduleTask).where(
                ConstructionScheduleTask.construction_project_id == project_id,
            )
        ).all()
    }
    if not task_ids:
        return []
    return db.scalars(
        select(ConstructionScheduleDependency)
        .where(ConstructionScheduleDependency.predecessor_id.in_(task_ids))
        .order_by(ConstructionScheduleDependency.created_at.asc())
    ).all()


@router.post(
    "/projects/{project_id}/schedule/dependencies",
    response_model=ScheduleDependencyOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def create_dependency(
    project_id: str,
    payload: ScheduleDependencyCreate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = ConstructionScheduleDependency(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get(
    "/projects/{project_id}/schedule/dependencies/{dep_id}",
    response_model=ScheduleDependencyOut,
)
def get_dependency(
    project_id: str,
    dep_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    get_project_or_404(db, project_id)
    return _get_or_404(
        db, ConstructionScheduleDependency, dep_id, "Schedule dependency",
    )


@router.patch(
    "/projects/{project_id}/schedule/dependencies/{dep_id}",
    response_model=ScheduleDependencyOut,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def update_dependency(
    project_id: str,
    dep_id: str,
    payload: ScheduleDependencyUpdate,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(
        db, ConstructionScheduleDependency, dep_id, "Schedule dependency",
    )
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/projects/{project_id}/schedule/dependencies/{dep_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*PM_ROLES))],
)
def delete_dependency(
    project_id: str,
    dep_id: str,
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    obj = _get_or_404(
        db, ConstructionScheduleDependency, dep_id, "Schedule dependency",
    )
    db.delete(obj)
    db.commit()
