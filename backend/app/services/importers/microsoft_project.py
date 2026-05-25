"""Microsoft Project XML importer.

The proprietary ``.mpp`` binary format isn't readable without third-party
deps; MS Project can save to "Project XML" (``.xml``), which we parse with
stdlib ``xml.etree.ElementTree``.

A Project XML document looks roughly like:

    <Project xmlns="http://schemas.microsoft.com/project">
      <Name>Office Move</Name>
      <Tasks>
        <Task>
          <UID>1</UID>
          <Name>Pack desks</Name>
          <OutlineLevel>1</OutlineLevel>
          <Start>2026-06-01T08:00:00</Start>
          <Finish>2026-06-03T17:00:00</Finish>
          <PredecessorLink>
            <PredecessorUID>0</PredecessorUID>
            <Type>1</Type>
          </PredecessorLink>
        </Task>
        ...
      </Tasks>
      <Resources>
        <Resource><UID>1</UID><Name>Alice</Name></Resource>
        ...
      </Resources>
    </Project>

We map:
* ``Project/Name`` → :class:`Project`
* each ``Task`` → :class:`Task`, recording the UID in ``tags`` as
  ``msp:<uid>`` so dependencies can later resolve UIDs to task ids.
* each ``Resource`` → :class:`Resource` (or skipped if no Resource model
  exposed — we always do, since the model exists).
* each ``PredecessorLink`` → :class:`TaskDependency`.

OutlineLevel: the suite's Task model has no ``parent_task_id`` column,
so we surface WBS hierarchy as a ``WBS=<n.n.n>`` prefix in ``Task.tags``.
This keeps the hierarchy queryable without a schema change.

Dedup: by UID within the same project.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.import_jobs import ImportJob
from app.models.projects import Resource, Task, TaskDependency
from app.services.importers._project_base import (
    ensure_tenant,
    get_or_create_project,
    parse_date,
    rollback_project_records,
)
from app.services.importers.base import Importer


MSP_NS_PREFIXES = (
    "{http://schemas.microsoft.com/project}",
    "",  # also support namespace-less XML the way Project 2007 sometimes emits
)


def _child_text(elem: ET.Element, tag: str) -> str:
    """Return text of the first child matching ``tag``, with or without ns."""
    for prefix in MSP_NS_PREFIXES:
        found = elem.find(f"{prefix}{tag}")
        if found is not None and found.text is not None:
            return found.text.strip()
    return ""


def _children(elem: ET.Element, tag: str) -> list[ET.Element]:
    for prefix in MSP_NS_PREFIXES:
        found = elem.findall(f"{prefix}{tag}")
        if found:
            return found
    return []


class MicrosoftProjectImporter(Importer):
    source = "microsoft_project"
    supported_entities = ["project", "tasks", "resources", "dependencies"]
    description = "Microsoft Project XML (Project XML / .xml export)"

    # ---- discovery ---------------------------------------------------------

    def detect_schema(self, file_path: Path) -> dict[str, Any]:
        try:
            tree = ET.parse(file_path)
        except ET.ParseError as exc:
            return {
                "columns": [],
                "sample_rows": [],
                "inferred_types": {},
                "error": f"Invalid XML: {exc}",
            }
        root = tree.getroot()
        project_name = _child_text(root, "Name")
        tasks_root = None
        for prefix in MSP_NS_PREFIXES:
            tasks_root = root.find(f"{prefix}Tasks")
            if tasks_root is not None:
                break
        task_elems = list(tasks_root) if tasks_root is not None else []
        # The "columns" here describe a Task element's children. Stable set.
        columns = ["UID", "Name", "OutlineLevel", "Start", "Finish", "PercentComplete", "Priority"]
        sample: list[dict[str, Any]] = []
        for t in task_elems[:5]:
            sample.append({c: _child_text(t, c) for c in columns})
        return {
            "columns": columns,
            "sample_rows": sample,
            "inferred_types": {c: "string" for c in columns},
            "project_name": project_name,
            "task_count": len(task_elems),
        }

    def suggest_mapping(
        self, source_columns: list[str], target_entity: str
    ) -> dict[str, str]:
        if target_entity in ("tasks", "project"):
            return {
                "UID": "external_id",
                "Name": "title",
                "OutlineLevel": "outline_level",
                "Start": "start_date",
                "Finish": "due_date",
                "PercentComplete": "progress",
                "Notes": "description",
            }
        if target_entity == "resources":
            return {"UID": "external_id", "Name": "name"}
        return {}

    def required_fields(self, target_entity: str) -> list[str]:
        if target_entity in ("tasks", "project"):
            return ["title"]
        if target_entity == "resources":
            return ["name"]
        return []

    # ---- validate ----------------------------------------------------------

    def validate(self, job: ImportJob, db: Session) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        if not job.source_file_path:
            return [{"row": 0, "severity": "error", "column": None,
                     "message": "Job has no uploaded file"}]
        path = Path(job.source_file_path)
        if not path.exists():
            return [{"row": 0, "severity": "error", "column": None,
                     "message": "Uploaded file is missing"}]
        try:
            tree = ET.parse(path)
        except ET.ParseError as exc:
            return [{"row": 0, "severity": "error", "column": None,
                     "message": f"Invalid XML: {exc}"}]
        root = tree.getroot()
        tasks_root = None
        for prefix in MSP_NS_PREFIXES:
            tasks_root = root.find(f"{prefix}Tasks")
            if tasks_root is not None:
                break
        if tasks_root is None:
            issues.append({"row": 0, "severity": "error", "column": "Tasks",
                           "message": "Project XML has no <Tasks> element"})
            return issues
        for i, t in enumerate(list(tasks_root), start=1):
            name = _child_text(t, "Name")
            if not name:
                issues.append({"row": i, "severity": "error", "column": "Name",
                               "message": f"Task {i}: missing <Name>"})
        return issues

    # ---- preview -----------------------------------------------------------

    def preview(
        self, job: ImportJob, db: Session, limit: int = 10
    ) -> list[dict[str, Any]]:
        if not job.source_file_path:
            return []
        path = Path(job.source_file_path)
        if not path.exists():
            return []
        try:
            tree = ET.parse(path)
        except ET.ParseError:
            return []
        root = tree.getroot()
        tasks_root = None
        for prefix in MSP_NS_PREFIXES:
            tasks_root = root.find(f"{prefix}Tasks")
            if tasks_root is not None:
                break
        if tasks_root is None:
            return []
        out: list[dict[str, Any]] = []
        for t in list(tasks_root)[:limit]:
            out.append({
                "title": _child_text(t, "Name"),
                "start_date": _child_text(t, "Start")[:10] or None,
                "due_date": _child_text(t, "Finish")[:10] or None,
                "outline_level": _child_text(t, "OutlineLevel") or None,
            })
        return out

    # ---- commit ------------------------------------------------------------

    def import_rows(self, job: ImportJob, db: Session) -> ImportJob:
        path = Path(job.source_file_path) if job.source_file_path else None
        if not path or not path.exists():
            job.status = "failed"
            return job
        try:
            tree = ET.parse(path)
        except ET.ParseError as exc:
            job.status = "failed"
            self._record_error(db, job, 0, {}, "validation", f"Invalid XML: {exc}")
            return job
        root = tree.getroot()

        # ---- Project ------------------------------------------------------
        project_name_in_xml = _child_text(root, "Name")
        project_name = (
            (job.options or {}).get("project_name")
            or project_name_in_xml
            or "Imported MSP Project"
        )
        project = get_or_create_project(db, project_name)
        imported_ids: list[list[Any]] = list(job.imported_record_ids or [])
        if not db.scalar(select(Task).where(Task.project_id == project.id)):
            imported_ids.append(["project", project.id])

        # ---- Resources (optional) ----------------------------------------
        resources_root = None
        for prefix in MSP_NS_PREFIXES:
            resources_root = root.find(f"{prefix}Resources")
            if resources_root is not None:
                break
        resource_uid_to_id: dict[str, str] = {}
        if resources_root is not None and job.target_entity in ("project", "resources"):
            for r in list(resources_root):
                name = _child_text(r, "Name")
                uid = _child_text(r, "UID")
                if not name:
                    continue
                # Dedup by name within tenant
                existing = db.scalar(select(Resource).where(Resource.name == name))
                if existing is not None:
                    resource_uid_to_id[uid] = existing.id
                    continue
                res = ensure_tenant(Resource(name=name[:180]))
                db.add(res)
                db.flush()
                resource_uid_to_id[uid] = res.id
                imported_ids.append(["resource", res.id])

        # ---- Tasks --------------------------------------------------------
        tasks_root = None
        for prefix in MSP_NS_PREFIXES:
            tasks_root = root.find(f"{prefix}Tasks")
            if tasks_root is not None:
                break
        task_elems = list(tasks_root) if tasks_root is not None else []

        # First pass: preload existing markers for cross-run dedup
        existing_markers: set[str] = set()
        for existing in db.scalars(
            select(Task).where(Task.project_id == project.id)
        ):
            for token in (existing.tags or "").split():
                if token.startswith("msp:"):
                    existing_markers.add(token[len("msp:"):])

        # WBS counter per outline level
        wbs_counter: dict[int, int] = {}

        uid_to_task_id: dict[str, str] = {}
        row_no = imported = skipped = failed = 0
        seen_uids: set[str] = set()

        for t in task_elems:
            row_no += 1
            try:
                name = _child_text(t, "Name")
                uid = _child_text(t, "UID")
                if not name:
                    self._record_error(
                        db, job, row_no, {"UID": uid},
                        "missing_required_field",
                        f"Task {row_no}: missing <Name>",
                    )
                    failed += 1
                    continue
                if uid and uid in seen_uids:
                    skipped += 1
                    continue
                if uid and uid in existing_markers:
                    skipped += 1
                    seen_uids.add(uid)
                    continue
                seen_uids.add(uid)

                outline_raw = _child_text(t, "OutlineLevel")
                try:
                    outline_level = int(outline_raw) if outline_raw else 1
                except ValueError:
                    outline_level = 1
                # Update WBS counter
                wbs_counter[outline_level] = wbs_counter.get(outline_level, 0) + 1
                # Reset deeper levels
                for lvl in list(wbs_counter):
                    if lvl > outline_level:
                        wbs_counter[lvl] = 0
                wbs = ".".join(
                    str(wbs_counter[l])
                    for l in sorted(wbs_counter)
                    if l <= outline_level and wbs_counter[l] > 0
                ) or "1"

                tag_parts: list[str] = []
                if uid:
                    tag_parts.append(f"msp:{uid}")
                tag_parts.append(f"WBS={wbs}")
                tags = " ".join(tag_parts)[:255]

                pct_raw = _child_text(t, "PercentComplete")
                try:
                    progress = int(pct_raw) if pct_raw else 0
                except ValueError:
                    progress = 0

                task = ensure_tenant(Task(
                    project_id=project.id,
                    title=name[:180],
                    description=_child_text(t, "Notes")[:65535],
                    start_date=parse_date(_child_text(t, "Start")),
                    due_date=parse_date(_child_text(t, "Finish")),
                    tags=tags,
                ))
                db.add(task)
                db.flush()
                if uid:
                    uid_to_task_id[uid] = task.id
                imported += 1
                imported_ids.append(["task", task.id])
                _ = progress  # progress reserved for future Task.progress column
            except Exception as exc:  # pragma: no cover - defensive
                self._record_error(
                    db, job, row_no,
                    {"UID": _child_text(t, "UID"), "Name": _child_text(t, "Name")},
                    "unknown", str(exc),
                )
                failed += 1

        # ---- Dependencies -------------------------------------------------
        if job.target_entity in ("project", "dependencies"):
            for t in task_elems:
                this_uid = _child_text(t, "UID")
                this_task_id = uid_to_task_id.get(this_uid)
                if not this_task_id:
                    continue
                for link in _children(t, "PredecessorLink"):
                    pred_uid = _child_text(link, "PredecessorUID")
                    pred_task_id = uid_to_task_id.get(pred_uid)
                    if not pred_task_id:
                        continue
                    if pred_task_id == this_task_id:
                        continue
                    # Skip dupes (UID pair) already in DB for this project
                    existing_dep = db.scalar(
                        select(TaskDependency)
                        .where(TaskDependency.task_id == this_task_id)
                        .where(TaskDependency.depends_on_task_id == pred_task_id)
                    )
                    if existing_dep is not None:
                        continue
                    dep = ensure_tenant(TaskDependency(
                        task_id=this_task_id,
                        depends_on_task_id=pred_task_id,
                        dep_type="finish_to_start",
                    ))
                    db.add(dep)
                    db.flush()
                    imported_ids.append(["task_dependency", dep.id])

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
