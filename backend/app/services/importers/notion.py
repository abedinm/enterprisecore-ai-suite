"""Notion CSV importer.

Notion exports one CSV per database; columns vary per database, but the
common shapes are:

* Tasks DB:  ``Name``, ``Status``, ``Assignee``, ``Due``, ``Tags``, ``Description``
* Notes DB:  ``Name``, ``Tags``, ``Created``, plus a long free-form column

We treat Notion as a "smart generic CSV" — the user can map any column to
any EC field, but :meth:`suggest_mapping` pre-fills the obvious matches
using Notion's column conventions (``Name`` → title, ``Due`` → due_date,
``Status`` → status, etc.).

Supported entities:
    * ``tasks`` → :class:`Task` (under one project derived from filename
      or the ``project_name`` option)
    * ``notes`` → :class:`Document` (longer-form content)

Dedup: by ``Name`` within the same project (tasks) / within the tenant
(notes). Notion doesn't ship a stable per-row external ID in its CSV
export.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documents import Document
from app.models.import_jobs import ImportJob
from app.models.projects import Task
from app.services.importers._project_base import (
    ensure_tenant,
    get_or_create_project,
    parse_date,
    rollback_project_records,
    status_from_section,
)
from app.services.importers.base import MAX_ROWS_PER_FILE, Importer, _apply_mapping


# Notion column header → EC field, case-insensitive lookup.
# Multiple synonyms exist because users rename Notion columns frequently.
NOTION_TASK_SYNONYMS: dict[str, list[str]] = {
    "title": ["name", "task", "title"],
    "status": ["status", "state", "stage"],
    "assignee_name": ["assignee", "owner", "person", "assigned to"],
    "due_date": ["due", "due date", "deadline", "date"],
    "tags": ["tags", "labels", "category"],
    "description": ["description", "notes", "details", "summary", "body"],
}

NOTION_NOTE_SYNONYMS: dict[str, list[str]] = {
    "title": ["name", "title"],
    "content": ["content", "body", "notes", "description", "page content", "text"],
    "tags": ["tags", "labels", "category"],
}


def _lookup_field(col: str, syn_table: dict[str, list[str]]) -> str | None:
    norm = col.strip().lower()
    for ec_field, syns in syn_table.items():
        if norm in {s.lower() for s in syns}:
            return ec_field
    # Substring fallback — handles "Due Date 📅" etc.
    for ec_field, syns in syn_table.items():
        for s in syns:
            if s.lower() and s.lower() in norm:
                return ec_field
    return None


class NotionImporter(Importer):
    source = "notion"
    supported_entities = ["tasks", "notes"]
    description = "Notion (database CSV exports → tasks / notes)"

    # ---- discovery ---------------------------------------------------------

    def suggest_mapping(
        self, source_columns: list[str], target_entity: str
    ) -> dict[str, str]:
        syn_table = (
            NOTION_TASK_SYNONYMS if target_entity == "tasks" else NOTION_NOTE_SYNONYMS
        )
        out: dict[str, str] = {}
        used: set[str] = set()
        for col in source_columns:
            ec = _lookup_field(col, syn_table)
            if ec and ec not in used:
                out[col] = ec
                used.add(ec)
        return out

    def required_fields(self, target_entity: str) -> list[str]:
        if target_entity == "tasks":
            return ["title"]
        if target_entity == "notes":
            return ["title"]
        return []

    # ---- commit ------------------------------------------------------------

    def import_rows(self, job: ImportJob, db: Session) -> ImportJob:
        path = Path(job.source_file_path) if job.source_file_path else None
        if not path or not path.exists():
            job.status = "failed"
            return job

        mapping = job.column_mapping or {}
        if not mapping:
            first = next(iter(self._iter_rows(path, limit=1)), {})
            mapping = self.suggest_mapping(list(first.keys()), job.target_entity)

        if job.target_entity == "tasks":
            return self._import_tasks(job, db, path, mapping)
        return self._import_notes(job, db, path, mapping)

    def _import_tasks(
        self, job: ImportJob, db: Session, path: Path, mapping: dict[str, str]
    ) -> ImportJob:
        options = dict(job.options or {})
        project_name = options.get("project_name") or _derive_project_name(job, "Notion Import")
        project = get_or_create_project(db, project_name)
        imported_ids: list[list[Any]] = list(job.imported_record_ids or [])
        if not db.scalar(select(Task).where(Task.project_id == project.id)):
            imported_ids.append(["project", project.id])

        row_no = imported = skipped = failed = 0
        seen_titles: set[str] = set()
        for raw in self._iter_rows(path):
            row_no += 1
            if row_no > MAX_ROWS_PER_FILE:
                break
            mapped = _apply_mapping(raw, mapping)
            title = (mapped.get("title") or "").strip()
            if not title:
                self._record_error(
                    db, job, row_no, raw, "missing_required_field",
                    f"Row {row_no}: missing required field 'title'",
                )
                failed += 1
                continue
            key = title.lower()
            if key in seen_titles:
                skipped += 1
                continue
            existing = db.scalar(
                select(Task)
                .where(Task.project_id == project.id)
                .where(Task.title == title[:180])
            )
            if existing is not None:
                skipped += 1
                seen_titles.add(key)
                continue
            seen_titles.add(key)
            task = ensure_tenant(Task(
                project_id=project.id,
                title=title[:180],
                description=(mapped.get("description") or "")[:65535],
                status=status_from_section(mapped.get("status") or ""),
                due_date=parse_date(mapped.get("due_date")),
                tags=(mapped.get("tags") or "")[:255],
            ))
            db.add(task)
            db.flush()
            imported += 1
            imported_ids.append(["task", task.id])

        job.row_count_total = row_no
        job.row_count_imported = imported
        job.row_count_skipped = skipped
        job.row_count_failed = failed
        job.imported_record_ids = imported_ids
        job.status = "completed"
        job.completed_at = datetime.now()
        db.flush()
        return job

    def _import_notes(
        self, job: ImportJob, db: Session, path: Path, mapping: dict[str, str]
    ) -> ImportJob:
        imported_ids: list[list[Any]] = list(job.imported_record_ids or [])
        row_no = imported = skipped = failed = 0
        seen_titles: set[str] = set()
        for raw in self._iter_rows(path):
            row_no += 1
            if row_no > MAX_ROWS_PER_FILE:
                break
            mapped = _apply_mapping(raw, mapping)
            title = (mapped.get("title") or "").strip()
            if not title:
                self._record_error(
                    db, job, row_no, raw, "missing_required_field",
                    f"Row {row_no}: missing required field 'title'",
                )
                failed += 1
                continue
            key = title.lower()
            if key in seen_titles:
                skipped += 1
                continue
            existing = db.scalar(select(Document).where(Document.title == title[:220]))
            if existing is not None:
                skipped += 1
                seen_titles.add(key)
                continue
            seen_titles.add(key)
            doc = ensure_tenant(Document(
                title=title[:220],
                content=(mapped.get("content") or "")[:65535],
            ))
            db.add(doc)
            db.flush()
            imported += 1
            imported_ids.append(["note", doc.id])

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


def _derive_project_name(job: ImportJob, default: str) -> str:
    if job.source_file_path:
        stem = Path(job.source_file_path).stem
        if stem and not stem.startswith(("tmp", "notion_")):
            return f"Notion: {stem}"
    return default
