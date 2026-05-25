"""Asana CSV importer.

Asana's "Export to CSV" produces one row per task with these columns:

    Task ID, Created At, Completed At, Last Modified, Name,
    Section/Column, Assignee, Due Date, Tags, Notes

We map:
* the *file's* derived name (or the user-provided ``project_name`` option) →
  a single suite :class:`Project`
* every row → a suite :class:`Task` under that project. ``Section/Column``
  is mapped through :func:`status_from_section` to ``Task.status`` and the
  ``Notes`` body lands in ``Task.description``.

Dedup: by ``Task ID`` *within the same project* (Asana IDs are globally
unique but we still scope to the project so re-importing a different
board's CSV that happens to collide is impossible). The Task model
doesn't have an ``external_id`` column, so we stash the Asana ID in the
first 24 chars of ``Task.tags`` prefixed ``asana:`` (collision-free with
the user's tag strings, which never start with ``asana:``).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.import_jobs import ImportJob
from app.models.projects import Project, Task
from app.services.importers._project_base import (
    ensure_tenant,
    get_or_create_project,
    parse_date,
    rollback_project_records,
    status_from_section,
)
from app.services.importers.base import MAX_ROWS_PER_FILE, Importer, _apply_mapping


# Auto-mapping for the canonical Asana column header set.
ASANA_DEFAULT_MAPPING: dict[str, str] = {
    "Task ID": "external_id",
    "Name": "title",
    "Section/Column": "status",
    "Assignee": "assignee_name",
    "Due Date": "due_date",
    "Tags": "tags",
    "Notes": "description",
    "Created At": "created_at_source",
    "Completed At": "completed_at_source",
}


class AsanaImporter(Importer):
    source = "asana"
    supported_entities = ["project", "tasks"]
    description = "Asana (Project → tasks CSV export)"

    # ---- discovery ---------------------------------------------------------

    def suggest_mapping(
        self, source_columns: list[str], target_entity: str
    ) -> dict[str, str]:
        out: dict[str, str] = {}
        for col in source_columns:
            mapped = ASANA_DEFAULT_MAPPING.get(col.strip())
            if mapped:
                out[col] = mapped
        return out

    def required_fields(self, target_entity: str) -> list[str]:
        if target_entity in ("project", "tasks"):
            return ["title"]
        return []

    # ---- commit ------------------------------------------------------------

    def import_rows(self, job: ImportJob, db: Session) -> ImportJob:
        options = dict(job.options or {})
        project_name = options.get("project_name") or _derive_project_name(job)
        path = Path(job.source_file_path) if job.source_file_path else None
        if not path or not path.exists():
            job.status = "failed"
            return job

        mapping = job.column_mapping or self.suggest_mapping(
            list(next(iter(self._iter_rows(path, limit=1)), {}).keys()),
            job.target_entity,
        )

        imported_ids: list[list[Any]] = list(job.imported_record_ids or [])
        # Create the project up-front so even a 0-task CSV still yields one.
        project = get_or_create_project(db, project_name)
        # Only track the project for rollback if WE created it (i.e. it has no other tasks)
        if not db.scalar(select(Task).where(Task.project_id == project.id)):
            imported_ids.append(["project", project.id])

        row_no = 0
        imported = skipped = failed = 0
        seen_ext_ids: set[str] = set()

        for raw in self._iter_rows(path):
            row_no += 1
            if row_no > MAX_ROWS_PER_FILE:
                self._record_error(
                    db, job, row_no, raw, "unknown",
                    f"Stopped at row {row_no}: exceeds {MAX_ROWS_PER_FILE} safety cap",
                )
                failed += 1
                break
            try:
                mapped = _apply_mapping(raw, mapping)
                title = (mapped.get("title") or "").strip()
                if not title:
                    self._record_error(
                        db, job, row_no, raw, "missing_required_field",
                        f"Row {row_no}: missing required field 'title'",
                    )
                    failed += 1
                    continue

                ext_id = (mapped.get("external_id") or "").strip()
                # Within-file dedup
                if ext_id and ext_id in seen_ext_ids:
                    skipped += 1
                    continue
                # Cross-run dedup against the same project
                if ext_id:
                    tag_marker = f"asana:{ext_id}"
                    existing = db.scalar(
                        select(Task)
                        .where(Task.project_id == project.id)
                        .where(Task.tags.like(f"%{tag_marker}%"))
                    )
                    if existing is not None:
                        skipped += 1
                        seen_ext_ids.add(ext_id)
                        continue
                    seen_ext_ids.add(ext_id)

                tags_value = (mapped.get("tags") or "").strip()
                if ext_id:
                    marker = f"asana:{ext_id}"
                    tags_value = f"{marker} {tags_value}".strip()

                task = ensure_tenant(Task(
                    project_id=project.id,
                    title=title[:180],
                    description=(mapped.get("description") or "")[:65535],
                    status=status_from_section(mapped.get("status") or ""),
                    due_date=parse_date(mapped.get("due_date")),
                    tags=tags_value[:255],
                ))
                db.add(task)
                db.flush()
                imported += 1
                imported_ids.append(["task", task.id])
            except Exception as exc:  # pragma: no cover - defensive
                self._record_error(db, job, row_no, raw, "unknown", str(exc))
                failed += 1

        job.row_count_total = row_no
        job.row_count_imported = imported
        job.row_count_skipped = skipped
        job.row_count_failed = failed
        job.imported_record_ids = imported_ids
        job.status = "completed"
        job.completed_at = datetime.now()
        db.flush()
        return job

    def rollback(self, job: ImportJob, db: Session) -> None:
        rollback_project_records(job, db)


def _derive_project_name(job: ImportJob) -> str:
    """Default to the upload filename stem if the caller didn't pass one."""
    if job.source_file_path:
        stem = Path(job.source_file_path).stem
        if stem and not stem.startswith(("tmp", "asana_")):
            return f"Asana: {stem}"
    return "Asana Import"
