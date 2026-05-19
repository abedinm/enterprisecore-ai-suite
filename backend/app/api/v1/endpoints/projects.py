"""Project management endpoints — Kanban, Gantt, sprints, time tracking, milestones, workload, meetings, analytics."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.projects import (
    Meeting, MeetingMinute, Milestone, Project, Resource, ResourceAllocation,
    Sprint, Task, TaskDependency, TimeEntry,
)
from app.models.user import User, UserRole
from app.schemas.projects import (
    MeetingIn, MeetingMinuteIn, MeetingMinuteOut, MeetingOut, MilestoneIn,
    MilestoneOut, ProjectAnalyticsOut, ProjectIn, ProjectOut,
    ResourceAllocationIn, ResourceAllocationOut, ResourceIn, ResourceOut,
    SprintIn, SprintOut, TaskDependencyIn, TaskDependencyOut, TaskIn, TaskOut,
    TaskStatusUpdate, TimeEntryIn, TimeEntryOut,
)

router = APIRouter()
KANBAN_COLUMNS = ["backlog", "todo", "in_progress", "in_review", "done"]


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
def list_projects(status: str | None = None, q: str | None = None,
                  db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    stmt = select(Project).order_by(Project.created_at.desc())
    if status:
        stmt = stmt.where(Project.status == status)
    if q:
        stmt = stmt.where(or_(Project.name.ilike(f"%{q}%"), Project.description.ilike(f"%{q}%")))
    return db.scalars(stmt).all()


@router.get("/projects/{pid}", response_model=ProjectOut)
def get_project(pid: str, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    obj = db.get(Project, pid)
    if not obj:
        raise NotFoundError("Project not found")
    return obj


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
               status: str | None = None, sprint_id: str | None = None,
               priority: str | None = None, q: str | None = None,
               db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(Task).order_by(Task.position, Task.due_date.nullslast(), Task.created_at.desc())
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    if assignee_id:
        stmt = stmt.where(Task.assignee_id == assignee_id)
    if status:
        stmt = stmt.where(Task.status == status)
    if sprint_id:
        stmt = stmt.where(Task.sprint_id == sprint_id)
    if priority:
        stmt = stmt.where(Task.priority == priority)
    if q:
        stmt = stmt.where(or_(Task.title.ilike(f"%{q}%"), Task.description.ilike(f"%{q}%")))
    return db.scalars(stmt.limit(2000)).all()


@router.get("/tasks/kanban")
def kanban(project_id: str | None = None, sprint_id: str | None = None,
           db: Session = Depends(get_db),
           _: User = Depends(get_current_user)):
    stmt = select(Task).order_by(Task.position, Task.created_at.desc())
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    if sprint_id:
        stmt = stmt.where(Task.sprint_id == sprint_id)
    tasks = db.scalars(stmt).all()
    columns: dict[str, list] = {col: [] for col in KANBAN_COLUMNS}
    for t in tasks:
        columns.setdefault(t.status, []).append({
            "id": t.id, "title": t.title, "description": t.description, "priority": t.priority,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "assignee_id": t.assignee_id, "project_id": t.project_id,
            "sprint_id": t.sprint_id, "tags": t.tags, "story_points": t.story_points,
            "position": t.position,
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
    if payload.position is not None:
        t.position = payload.position
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


# ---- Task dependencies (Gantt) -----------------------------------------
@router.get("/dependencies", response_model=list[TaskDependencyOut])
def list_dependencies(task_id: str | None = None, db: Session = Depends(get_db),
                      _: User = Depends(get_current_user)):
    stmt = select(TaskDependency)
    if task_id:
        stmt = stmt.where(TaskDependency.task_id == task_id)
    return db.scalars(stmt).all()


@router.post("/dependencies", response_model=TaskDependencyOut)
def create_dependency(payload: TaskDependencyIn, db: Session = Depends(get_db),
                      _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(TaskDependency, db, payload)


@router.delete("/dependencies/{did}", status_code=204)
def delete_dependency(did: str, db: Session = Depends(get_db),
                      _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(TaskDependency, did)
    if obj:
        db.delete(obj)
        db.commit()


# ---- Gantt --------------------------------------------------------------
@router.get("/projects/{pid}/gantt")
def gantt(pid: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    project = db.get(Project, pid)
    if not project:
        raise NotFoundError("Project not found")
    tasks = db.scalars(select(Task).where(Task.project_id == pid).order_by(Task.start_date.nullslast())).all()
    milestones = db.scalars(select(Milestone).where(Milestone.project_id == pid)).all()
    task_ids = [t.id for t in tasks]
    deps = []
    if task_ids:
        deps = db.scalars(select(TaskDependency).where(TaskDependency.task_id.in_(task_ids))).all()
    return {
        "project": {
            "id": project.id, "name": project.name,
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "end_date": project.end_date.isoformat() if project.end_date else None,
            "color": project.color, "progress": project.progress,
        },
        "tasks": [{
            "id": t.id, "title": t.title, "status": t.status,
            "start_date": t.start_date.isoformat() if t.start_date else None,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "priority": t.priority, "assignee_id": t.assignee_id,
            "estimated_hours": float(t.estimated_hours), "actual_hours": float(t.actual_hours),
        } for t in tasks],
        "milestones": [{
            "id": m.id, "title": m.title, "status": m.status,
            "due_date": m.due_date.isoformat() if m.due_date else None,
            "progress": m.progress,
        } for m in milestones],
        "dependencies": [{"id": d.id, "task_id": d.task_id, "depends_on_task_id": d.depends_on_task_id,
                         "dep_type": d.dep_type} for d in deps],
    }


# ---- Sprints ------------------------------------------------------------
@router.get("/sprints", response_model=list[SprintOut])
def list_sprints(project_id: str | None = None, status: str | None = None,
                 db: Session = Depends(get_db),
                 _: User = Depends(get_current_user)):
    stmt = select(Sprint).order_by(Sprint.start_date.desc())
    if project_id:
        stmt = stmt.where(Sprint.project_id == project_id)
    if status:
        stmt = stmt.where(Sprint.status == status)
    return db.scalars(stmt).all()


@router.post("/sprints", response_model=SprintOut)
def create_sprint(payload: SprintIn, db: Session = Depends(get_db),
                  _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Sprint, db, payload)


@router.patch("/sprints/{sid}", response_model=SprintOut)
def update_sprint(sid: str, payload: SprintIn, db: Session = Depends(get_db),
                  _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Sprint, db, payload, item_id=sid)


@router.delete("/sprints/{sid}", status_code=204)
def delete_sprint(sid: str, db: Session = Depends(get_db),
                  _: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(Sprint, sid)
    if obj:
        db.delete(obj)
        db.commit()


@router.get("/sprints/{sid}/burndown")
def sprint_burndown(sid: str, db: Session = Depends(get_db),
                    _: User = Depends(get_current_user)):
    sprint = db.get(Sprint, sid)
    if not sprint:
        raise NotFoundError("Sprint not found")
    tasks = db.scalars(select(Task).where(Task.sprint_id == sid)).all()
    total_points = sum(t.story_points for t in tasks) or 1
    days = (sprint.end_date - sprint.start_date).days or 1
    completed_points = sum(t.story_points for t in tasks if t.status == "done")
    ideal = []
    actual = []
    today = date.today()
    for i in range(days + 1):
        d = sprint.start_date + timedelta(days=i)
        ideal_pts = total_points - (total_points * i / days)
        ideal.append({"date": d.isoformat(), "points": round(ideal_pts, 1)})
        if d <= today:
            done_on_day = sum(t.story_points for t in tasks
                              if t.status == "done" and t.updated_at and t.updated_at.date() <= d)
            actual.append({"date": d.isoformat(), "points": total_points - done_on_day})
    return {
        "sprint_id": sid, "name": sprint.name,
        "start_date": sprint.start_date.isoformat(),
        "end_date": sprint.end_date.isoformat(),
        "total_points": total_points,
        "completed_points": completed_points,
        "remaining_points": total_points - completed_points,
        "ideal": ideal, "actual": actual,
        "task_count": len(tasks),
        "completed_tasks": sum(1 for t in tasks if t.status == "done"),
    }


# ---- Milestones ---------------------------------------------------------
@router.get("/milestones", response_model=list[MilestoneOut])
def list_milestones(project_id: str | None = None, status: str | None = None,
                    db: Session = Depends(get_db),
                    _: User = Depends(get_current_user)):
    stmt = select(Milestone).order_by(Milestone.due_date.nullslast())
    if project_id:
        stmt = stmt.where(Milestone.project_id == project_id)
    if status:
        stmt = stmt.where(Milestone.status == status)
    return db.scalars(stmt).all()


@router.post("/milestones", response_model=MilestoneOut)
def create_milestone(payload: MilestoneIn, db: Session = Depends(get_db),
                     _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Milestone, db, payload)


@router.patch("/milestones/{mid}", response_model=MilestoneOut)
def update_milestone(mid: str, payload: MilestoneIn, db: Session = Depends(get_db),
                     _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Milestone, db, payload, item_id=mid)


@router.delete("/milestones/{mid}", status_code=204)
def delete_milestone(mid: str, db: Session = Depends(get_db),
                     _: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(Milestone, mid)
    if obj:
        db.delete(obj)
        db.commit()


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
    if data.get("ended_at") and not data.get("minutes"):
        delta = data["ended_at"] - data["started_at"]
        data["minutes"] = max(int(delta.total_seconds() / 60), 0)
    obj = TimeEntry(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    # Update task actual hours
    if obj.task_id and obj.minutes:
        task = db.get(Task, obj.task_id)
        if task:
            task.actual_hours = Decimal(str(round(float(task.actual_hours) + obj.minutes / 60, 2)))
            db.commit()
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
    started = obj.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    delta = obj.ended_at - started
    obj.minutes = max(int(delta.total_seconds() / 60), 0)
    db.commit()
    db.refresh(obj)
    if obj.task_id and obj.minutes:
        task = db.get(Task, obj.task_id)
        if task:
            task.actual_hours = Decimal(str(round(float(task.actual_hours) + obj.minutes / 60, 2)))
            db.commit()
    return obj


@router.delete("/time-entries/{tid}", status_code=204)
def delete_time_entry(tid: str, db: Session = Depends(get_db),
                      _: User = Depends(get_current_user)):
    obj = db.get(TimeEntry, tid)
    if obj:
        db.delete(obj)
        db.commit()


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


@router.patch("/meetings/{mid}", response_model=MeetingOut)
def update_meeting(mid: str, payload: MeetingIn, db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    return _crud(Meeting, db, payload, item_id=mid)


@router.delete("/meetings/{mid}", status_code=204)
def delete_meeting(mid: str, db: Session = Depends(get_db),
                   _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(Meeting, mid)
    if obj:
        db.delete(obj)
        db.commit()


@router.get("/meetings/{mid}/minutes", response_model=list[MeetingMinuteOut])
def list_minutes(mid: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(
        select(MeetingMinute).where(MeetingMinute.meeting_id == mid).order_by(MeetingMinute.created_at)
    ).all()


@router.post("/meetings/{mid}/minutes", response_model=MeetingMinuteOut)
def add_minutes(mid: str, payload: MeetingMinuteIn, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    data = payload.model_dump()
    data["meeting_id"] = mid
    if not data.get("author_id"):
        data["author_id"] = current.id
    obj = MeetingMinute(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# ---- Resources & Allocations -------------------------------------------
@router.get("/resources", response_model=list[ResourceOut])
def list_resources(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Resource).order_by(Resource.name)).all()


@router.post("/resources", response_model=ResourceOut)
def create_resource(payload: ResourceIn, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Resource, db, payload)


@router.patch("/resources/{rid}", response_model=ResourceOut)
def update_resource(rid: str, payload: ResourceIn, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Resource, db, payload, item_id=rid)


@router.delete("/resources/{rid}", status_code=204)
def delete_resource(rid: str, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(Resource, rid)
    if obj:
        db.delete(obj)
        db.commit()


@router.get("/allocations", response_model=list[ResourceAllocationOut])
def list_allocations(project_id: str | None = None, resource_id: str | None = None,
                     db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(ResourceAllocation).order_by(ResourceAllocation.start_date.desc())
    if project_id:
        stmt = stmt.where(ResourceAllocation.project_id == project_id)
    if resource_id:
        stmt = stmt.where(ResourceAllocation.resource_id == resource_id)
    return db.scalars(stmt).all()


@router.post("/allocations", response_model=ResourceAllocationOut)
def create_allocation(payload: ResourceAllocationIn, db: Session = Depends(get_db),
                      _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(ResourceAllocation, db, payload)


@router.delete("/allocations/{aid}", status_code=204)
def delete_allocation(aid: str, db: Session = Depends(get_db),
                      _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(ResourceAllocation, aid)
    if obj:
        db.delete(obj)
        db.commit()


# ---- Workload visualizer ------------------------------------------------
@router.get("/workload")
def workload(project_id: str | None = None, db: Session = Depends(get_db),
             _: User = Depends(get_current_user)):
    """Compute current workload by assignee."""
    task_stmt = select(Task)
    if project_id:
        task_stmt = task_stmt.where(Task.project_id == project_id)
    tasks = db.scalars(task_stmt).all()

    by_user: dict[str, dict] = defaultdict(lambda: {
        "user_id": None, "name": "Unassigned",
        "total_tasks": 0, "in_progress": 0, "todo": 0, "done": 0,
        "overdue": 0, "estimated_hours": 0.0, "actual_hours": 0.0,
        "high_priority": 0,
    })
    today = date.today()
    for t in tasks:
        uid = t.assignee_id or "_unassigned"
        u = by_user[uid]
        u["user_id"] = t.assignee_id
        u["total_tasks"] += 1
        if t.status in u:
            u[t.status] = u.get(t.status, 0) + 1
        if t.due_date and t.due_date < today and t.status != "done":
            u["overdue"] += 1
        u["estimated_hours"] += float(t.estimated_hours)
        u["actual_hours"] += float(t.actual_hours)
        if t.priority == "high" or t.priority == "urgent":
            u["high_priority"] += 1

    # Hydrate names from users table
    user_ids = [uid for uid in by_user.keys() if uid != "_unassigned"]
    if user_ids:
        users = db.scalars(select(User).where(User.id.in_(user_ids))).all()
        for u in users:
            if u.id in by_user:
                by_user[u.id]["name"] = u.full_name

    return {"items": list(by_user.values())}


# ---- Scheduler (deadlines view) -----------------------------------------
@router.get("/scheduler/upcoming")
def scheduler_upcoming(days: int = 30, db: Session = Depends(get_db),
                       _: User = Depends(get_current_user)):
    horizon = date.today() + timedelta(days=days)
    today = date.today()
    tasks = db.scalars(
        select(Task).where(
            Task.due_date >= today, Task.due_date <= horizon, Task.status != "done"
        ).order_by(Task.due_date)
    ).all()
    milestones = db.scalars(
        select(Milestone).where(
            Milestone.due_date >= today, Milestone.due_date <= horizon,
            Milestone.status != "completed"
        ).order_by(Milestone.due_date)
    ).all()
    overdue_tasks = db.scalars(
        select(Task).where(Task.due_date < today, Task.status != "done")
    ).all()
    return {
        "today": today.isoformat(),
        "horizon_days": days,
        "tasks": [{
            "id": t.id, "title": t.title, "due_date": t.due_date.isoformat(),
            "priority": t.priority, "status": t.status, "project_id": t.project_id,
            "assignee_id": t.assignee_id,
        } for t in tasks],
        "milestones": [{
            "id": m.id, "title": m.title, "due_date": m.due_date.isoformat(),
            "status": m.status, "project_id": m.project_id, "progress": m.progress,
        } for m in milestones],
        "overdue": [{
            "id": t.id, "title": t.title,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "days_overdue": (today - t.due_date).days if t.due_date else 0,
            "priority": t.priority, "project_id": t.project_id, "assignee_id": t.assignee_id,
        } for t in overdue_tasks],
    }


# ---- Analytics ----------------------------------------------------------
@router.get("/analytics", response_model=ProjectAnalyticsOut)
def project_analytics(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    total = db.scalar(select(func.count(Project.id))) or 0
    active = db.scalar(select(func.count(Project.id)).where(Project.status == "active")) or 0
    completed = db.scalar(select(func.count(Project.id)).where(Project.status == "completed")) or 0
    by_status = {s: c for s, c in db.execute(select(Task.status, func.count(Task.id)).group_by(Task.status)).all()}
    by_priority = {p: c for p, c in db.execute(select(Task.priority, func.count(Task.id)).group_by(Task.priority)).all()}
    today = date.today()
    overdue = db.scalar(select(func.count(Task.id)).where(Task.due_date < today, Task.status != "done")) or 0
    upcoming = db.scalar(select(func.count(Milestone.id)).where(Milestone.due_date >= today, Milestone.status != "completed")) or 0
    total_minutes = db.scalar(select(func.coalesce(func.sum(TimeEntry.minutes), 0))) or 0
    total_tasks = db.scalar(select(func.count(Task.id))) or 0
    done_tasks = by_status.get("done", 0)
    completion_rate = round((done_tasks / total_tasks) * 100, 1) if total_tasks else 0.0

    # Avg task duration
    avg_dur_query = db.execute(
        select(func.avg(func.julianday(Task.due_date) - func.julianday(Task.start_date)))
        .where(Task.start_date.isnot(None), Task.due_date.isnot(None))
    ).scalar()
    avg_dur = round(float(avg_dur_query or 0), 1)

    # Sprint burn rate (story points done per active sprint)
    burn_rate: dict[str, int] = {}
    active_sprints = db.scalars(select(Sprint).where(Sprint.status == "active")).all()
    for s in active_sprints:
        done_pts = db.scalar(
            select(func.coalesce(func.sum(Task.story_points), 0))
            .where(Task.sprint_id == s.id, Task.status == "done")
        ) or 0
        burn_rate[s.name] = int(done_pts)

    # Workload by assignee
    workload_q = db.execute(
        select(Task.assignee_id, func.count(Task.id))
        .where(Task.status != "done")
        .group_by(Task.assignee_id)
    ).all()
    workload_list = [{"assignee_id": uid or "unassigned", "open_tasks": cnt} for uid, cnt in workload_q]

    # Project progress
    projects = db.scalars(select(Project)).all()
    project_progress = []
    for p in projects:
        p_tasks = db.scalars(select(Task).where(Task.project_id == p.id)).all()
        done = sum(1 for t in p_tasks if t.status == "done")
        total_p = len(p_tasks) or 1
        project_progress.append({
            "id": p.id, "name": p.name, "color": p.color,
            "total_tasks": len(p_tasks), "done_tasks": done,
            "progress": round((done / total_p) * 100, 1),
            "status": p.status,
        })

    # Upcoming deadlines (next 14 days)
    horizon = today + timedelta(days=14)
    upcoming_q = db.scalars(
        select(Task).where(Task.due_date >= today, Task.due_date <= horizon, Task.status != "done")
        .order_by(Task.due_date).limit(20)
    ).all()
    upcoming_deadlines = [{
        "id": t.id, "title": t.title, "due_date": t.due_date.isoformat(),
        "priority": t.priority, "days_left": (t.due_date - today).days,
    } for t in upcoming_q]

    return ProjectAnalyticsOut(
        total_projects=total, active_projects=active, completed_projects=completed,
        tasks_by_status=by_status, tasks_by_priority=by_priority,
        overdue_tasks=overdue, upcoming_milestones=upcoming,
        total_time_minutes=total_minutes,
        total_tasks=total_tasks, completed_tasks=done_tasks,
        completion_rate=completion_rate,
        avg_task_duration_days=avg_dur,
        sprint_burn_rate=burn_rate,
        workload_by_assignee=workload_list,
        project_progress=project_progress,
        upcoming_deadlines=upcoming_deadlines,
    )
