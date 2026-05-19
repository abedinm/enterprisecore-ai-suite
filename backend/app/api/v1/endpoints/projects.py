"""Project management endpoints — Kanban, Gantt, sprints, time tracking."""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.projects import (
    Meeting, MeetingMinute, Milestone, Project, Sprint, Task, TimeEntry,
)
from app.models.user import User, UserRole
from app.schemas.projects import (
    MeetingIn, MeetingMinuteIn, MeetingMinuteOut, MeetingOut, MilestoneIn,
    MilestoneOut, ProjectAnalyticsOut, ProjectIn, ProjectOut, SprintIn,
    SprintOut, TaskIn, TaskOut, TaskStatusUpdate, TimeEntryIn, TimeEntryOut,
)

router = APIRouter()
KANBAN_COLUMNS = ["todo", "in_progress", "in_review", "done"]


def _crud(model, db, payload, item_id=None):
    if item_id:
        obj = db.get(model, item_id)
        if not obj:
            raise NotFoundError(f"{model.__name__} not found")
        for k, v in payload.model_dump().items():
            setattr(obj, k, v)
    else:
        obj = model(**payload.model_dump())
        db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# ---- Projects -----------------------------------------------------------
@router.get("/projects", response_model=list[ProjectOut])
def list_projects(status: str | None = None, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    stmt = select(Project).order_by(Project.created_at.desc())
    if status:
        stmt = stmt.where(Project.status == status)
    return db.scalars(stmt).all()


@router.post("/projects", response_model=ProjectOut)
def create_project(payload: ProjectIn, db: Session = Depends(get_db),
                   _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Project, db, payload)


@router.patch("/projects/{pid}", response_model=ProjectOut)
def update_project(pid: str, payload: ProjectIn, db: Session = Depends(get_db),
                   _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Project, db, payload, item_id=pid)


@router.delete("/projects/{pid}", status_code=204)
def delete_project(pid: str, db: Session = Depends(get_db),
                   _: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(Project, pid)
    if obj:
        db.delete(obj)
        db.commit()


# ---- Tasks (Kanban) -----------------------------------------------------
@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(project_id: str | None = None, assignee_id: str | None = None,
               status: str | None = None, q: str | None = None,
               db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(Task).order_by(Task.due_date.nullslast(), Task.created_at.desc())
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    if assignee_id:
        stmt = stmt.where(Task.assignee_id == assignee_id)
    if status:
        stmt = stmt.where(Task.status == status)
    if q:
        stmt = stmt.where(or_(Task.title.ilike(f"%{q}%"), Task.description.ilike(f"%{q}%")))
    return db.scalars(stmt.limit(1000)).all()


@router.get("/tasks/kanban")
def kanban(project_id: str | None = None, db: Session = Depends(get_db),
           _: User = Depends(get_current_user)):
    stmt = select(Task).order_by(Task.created_at.desc())
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    tasks = db.scalars(stmt).all()
    columns: dict[str, list] = {col: [] for col in KANBAN_COLUMNS}
    for t in tasks:
        columns.setdefault(t.status, []).append({
            "id": t.id, "title": t.title, "priority": t.priority,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "assignee_id": t.assignee_id, "project_id": t.project_id,
        })
    return {"columns": [{"status": col, "tasks": columns[col]} for col in KANBAN_COLUMNS]}


@router.post("/tasks", response_model=TaskOut)
def create_task(payload: TaskIn, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    return _crud(Task, db, payload)


@router.patch("/tasks/{tid}", response_model=TaskOut)
def update_task(tid: str, payload: TaskIn, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    return _crud(Task, db, payload, item_id=tid)


@router.post("/tasks/{tid}/status", response_model=TaskOut)
def set_task_status(tid: str, payload: TaskStatusUpdate, db: Session = Depends(get_db),
                    _: User = Depends(get_current_user)):
    t = db.get(Task, tid)
    if not t:
        raise NotFoundError("Task not found")
    t.status = payload.status
    db.commit()
    db.refresh(t)
    return t


@router.delete("/tasks/{tid}", status_code=204)
def delete_task(tid: str, db: Session = Depends(get_db),
                _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(Task, tid)
    if obj:
        db.delete(obj)
        db.commit()


# ---- Gantt --------------------------------------------------------------
@router.get("/projects/{pid}/gantt")
def gantt(pid: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    project = db.get(Project, pid)
    if not project:
        raise NotFoundError("Project not found")
    tasks = db.scalars(select(Task).where(Task.project_id == pid)).all()
    milestones = db.scalars(select(Milestone).where(Milestone.project_id == pid)).all()
    return {
        "project": {"id": project.id, "name": project.name, "start_date": project.start_date,
                    "end_date": project.end_date},
        "tasks": [{
            "id": t.id, "title": t.title, "status": t.status,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "priority": t.priority, "assignee_id": t.assignee_id,
        } for t in tasks],
        "milestones": [{
            "id": m.id, "title": m.title, "status": m.status,
            "due_date": m.due_date.isoformat() if m.due_date else None,
        } for m in milestones],
    }


# ---- Sprints ------------------------------------------------------------
@router.get("/sprints", response_model=list[SprintOut])
def list_sprints(project_id: str | None = None, db: Session = Depends(get_db),
                 _: User = Depends(get_current_user)):
    stmt = select(Sprint).order_by(Sprint.start_date.desc())
    if project_id:
        stmt = stmt.where(Sprint.project_id == project_id)
    return db.scalars(stmt).all()


@router.post("/sprints", response_model=SprintOut)
def create_sprint(payload: SprintIn, db: Session = Depends(get_db),
                  _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Sprint, db, payload)


# ---- Milestones ---------------------------------------------------------
@router.get("/milestones", response_model=list[MilestoneOut])
def list_milestones(project_id: str | None = None, db: Session = Depends(get_db),
                    _: User = Depends(get_current_user)):
    stmt = select(Milestone).order_by(Milestone.due_date.nullslast())
    if project_id:
        stmt = stmt.where(Milestone.project_id == project_id)
    return db.scalars(stmt).all()


@router.post("/milestones", response_model=MilestoneOut)
def create_milestone(payload: MilestoneIn, db: Session = Depends(get_db),
                     _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Milestone, db, payload)


# ---- Time tracking ------------------------------------------------------
@router.get("/time-entries", response_model=list[TimeEntryOut])
def list_time_entries(task_id: str | None = None, user_id: str | None = None,
                      db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(TimeEntry).order_by(TimeEntry.started_at.desc())
    if task_id:
        stmt = stmt.where(TimeEntry.task_id == task_id)
    if user_id:
        stmt = stmt.where(TimeEntry.user_id == user_id)
    return db.scalars(stmt.limit(500)).all()


@router.post("/time-entries", response_model=TimeEntryOut)
def log_time(payload: TimeEntryIn, db: Session = Depends(get_db),
             current: User = Depends(get_current_user)):
    data = payload.model_dump()
    if not data.get("user_id"):
        data["user_id"] = current.id
    # Auto-compute minutes if ended_at provided
    if data.get("ended_at") and not data.get("minutes"):
        delta = data["ended_at"] - data["started_at"]
        data["minutes"] = max(int(delta.total_seconds() / 60), 0)
    obj = TimeEntry(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/time-entries/{tid}/stop", response_model=TimeEntryOut)
def stop_timer(tid: str, db: Session = Depends(get_db),
               _: User = Depends(get_current_user)):
    obj = db.get(TimeEntry, tid)
    if not obj:
        raise NotFoundError("Time entry not found")
    if obj.ended_at:
        return obj
    obj.ended_at = datetime.now(timezone.utc)
    delta = obj.ended_at - obj.started_at
    obj.minutes = max(int(delta.total_seconds() / 60), 0)
    db.commit()
    db.refresh(obj)
    return obj


# ---- Meetings -----------------------------------------------------------
@router.get("/meetings", response_model=list[MeetingOut])
def list_meetings(project_id: str | None = None, upcoming: bool = False,
                  db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(Meeting).order_by(Meeting.starts_at.desc())
    if project_id:
        stmt = stmt.where(Meeting.project_id == project_id)
    if upcoming:
        stmt = stmt.where(Meeting.starts_at >= datetime.now(timezone.utc))
    return db.scalars(stmt.limit(200)).all()


@router.post("/meetings", response_model=MeetingOut)
def create_meeting(payload: MeetingIn, db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    return _crud(Meeting, db, payload)


@router.get("/meetings/{mid}/minutes", response_model=list[MeetingMinuteOut])
def list_minutes(mid: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(
        select(MeetingMinute).where(MeetingMinute.meeting_id == mid).order_by(MeetingMinute.created_at)
    ).all()


@router.post("/meetings/{mid}/minutes", response_model=MeetingMinuteOut)
def add_minutes(mid: str, payload: MeetingMinuteIn, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    data = payload.model_dump()
    data["meeting_id"] = mid
    obj = MeetingMinute(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# ---- Analytics ----------------------------------------------------------
@router.get("/analytics", response_model=ProjectAnalyticsOut)
def project_analytics(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    total = db.scalar(select(func.count(Project.id))) or 0
    active = db.scalar(select(func.count(Project.id)).where(Project.status == "active")) or 0
    by_status = {s: c for s, c in db.execute(select(Task.status, func.count(Task.id)).group_by(Task.status)).all()}
    by_priority = {p: c for p, c in db.execute(select(Task.priority, func.count(Task.id)).group_by(Task.priority)).all()}
    today = date.today()
    overdue = db.scalar(select(func.count(Task.id)).where(Task.due_date < today, Task.status != "done")) or 0
    upcoming = db.scalar(select(func.count(Milestone.id)).where(Milestone.due_date >= today, Milestone.status != "completed")) or 0
    total_minutes = db.scalar(select(func.coalesce(func.sum(TimeEntry.minutes), 0))) or 0
    return ProjectAnalyticsOut(
        total_projects=total, active_projects=active,
        tasks_by_status=by_status, tasks_by_priority=by_priority,
        overdue_tasks=overdue, upcoming_milestones=upcoming,
        total_time_minutes=total_minutes,
    )
