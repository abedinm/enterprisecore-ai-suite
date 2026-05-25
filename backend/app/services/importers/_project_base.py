"""Shared helpers for project-management importers (Asana / Notion / Trello / MSP).

The CRM-focused :class:`CsvGenericImporter` targets contact / deal / invoice
rows. Project importers land into ``Project`` + ``Task`` (plus optionally
``Resource``, ``TaskDependency``, ``Document``) and need their own commit /
rollback paths. This module factors out the bits all four share so each
concrete importer can focus on its own file-format parsing.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant_context import get_current_tenant_id
from app.models.documents import Document
from app.models.import_jobs import ImportJob
from app.models.projects import Project, Resource, Task, TaskDependency


# Entity -> ORM class (used by rollback)
PROJECT_ENTITY_MODELS: dict[str, Any] = {
    "project": Project,
    "task": Task,
    "resource": Resource,
    "task_dependency": TaskDependency,
    "note": Document,
}


def parse_date(s: Any) -> date | None:
    """Parse the wide variety of date strings PM exports throw at us."""
    if s in (None, ""):
        return None
    text = str(s).strip()
    # Drop time component if present
    text_head = text.split("T")[0].split(" ")[0]
    for fmt in (
        "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y",
        "%m-%d-%Y", "%d-%m-%Y", "%Y%m%d",
    ):
        try:
            return datetime.strptime(text_head[:10], fmt).date()
        except ValueError:
            continue
    return None


def status_from_section(section: str) -> str:
    """Map a board column / section name to the EC task status enum."""
    if not section:
        return "todo"
    s = section.strip().lower()
    if s in {"done", "complete", "completed", "closed", "shipped", "finished"}:
        return "done"
    if s in {"in progress", "in-progress", "doing", "working", "active", "started"}:
        return "in_progress"
    if s in {"review", "in review", "qa", "testing"}:
        return "in_review"
    if s in {"blocked", "on hold", "paused"}:
        return "blocked"
    return "todo"


def ensure_tenant(obj: Any) -> Any:
    """Backfill ``tenant_id`` on a new ORM row from the current contextvar.

    The before_insert auto-set hook is skipped when the session is running
    under :func:`bypass_tenant_filter`, which is exactly the case for
    importer commits routed through the job queue. To keep the importers
    correct regardless of how they're invoked, every model we instantiate
    inside import_rows() goes through this helper.
    """
    if getattr(obj, "tenant_id", None):
        return obj
    tid = get_current_tenant_id()
    if tid and hasattr(obj, "tenant_id"):
        obj.tenant_id = tid
    return obj


def get_or_create_project(
    db: Session, name: str, *, description: str = ""
) -> Project:
    """Find an existing Project by name within the current tenant; else create."""
    if not name:
        name = "Imported Project"
    existing = db.scalar(select(Project).where(Project.name == name))
    if existing:
        return existing
    proj = ensure_tenant(
        Project(name=name[:180], description=description or "", status="active")
    )
    db.add(proj)
    db.flush()
    return proj


def rollback_project_records(job: ImportJob, db: Session) -> None:
    """Delete rows tracked in ``imported_record_ids`` for project-side entities.

    Each entry in ``imported_record_ids`` is ``[entity_key, pk]``.
    Order matters — dependents must be flushed before parents, otherwise
    the ``ON DELETE CASCADE`` on ``Task.project_id`` would wipe the tasks
    at the DB level before SQLAlchemy issues its own DELETE for them
    (which would then "miss" the rows and emit a warning). We group by
    entity type and flush between groups so each DELETE actually finds
    the rows it expects to remove.
    """
    if not job.imported_record_ids:
        return
    order = ["task_dependency", "note", "resource", "task", "project"]
    by_entity: dict[str, list] = {k: [] for k in order}
    for entry in job.imported_record_ids:
        try:
            entity, pk = entry
        except (ValueError, TypeError):
            continue
        if entity in by_entity:
            by_entity[entity].append(pk)
    for entity in order:
        pks = by_entity[entity]
        if not pks:
            continue
        model = PROJECT_ENTITY_MODELS.get(entity)
        if not model:
            continue
        for pk in pks:
            obj = db.get(model, pk)
            if obj is not None:
                db.delete(obj)
        # Flush between entity types so child deletes settle before the
        # parent delete triggers DB-level cascade.
        db.flush()
    job.imported_record_ids = []
    job.status = "rolled_back"
    db.flush()
