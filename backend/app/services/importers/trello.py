"""Trello JSON importer.

Trello → Settings → Export → JSON dumps the whole board as a single
JSON document:

    {
      "id": "...", "name": "Board name",
      "lists": [{"id": "...", "name": "To Do", "closed": false}, ...],
      "cards": [{"id": "...", "name": "...", "idList": "...", "due": ...,
                 "labels": [...], "idMembers": [...], "checklists": [...],
                 "desc": "..."}, ...],
      "members": [...],
      "labels": [...]
    }

We map:
* the board ``name`` → a suite :class:`Project`
* each ``card`` → a suite :class:`Task` under that project, ``idList``
  resolved to the list's ``name`` and run through
  :func:`status_from_section` for ``Task.status``. ``labels`` (joined by
  space) → ``Task.tags``. ``due`` → ``Task.due_date``.
* checklists are appended to ``Task.description`` as a markdown-ish
  outline since the Task model has no subtask field.

Dedup: by Trello card ``id`` within the project. Same external-id-in-tags
trick as the Asana importer (Task model has no ``external_id`` column).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.import_jobs import ImportJob
from app.models.projects import Task
from app.services.importers._project_base import (
    ensure_tenant,
    get_or_create_project,
    parse_date,
    rollback_project_records,
    status_from_section,
)
from app.services.importers.base import Importer


class TrelloImporter(Importer):
    source = "trello"
    supported_entities = ["board", "cards"]
    description = "Trello (board JSON export → project + tasks)"

    # ---- discovery ---------------------------------------------------------

    def detect_schema(self, file_path: Path) -> dict[str, Any]:
        data = _load_json(file_path)
        lists = data.get("lists", [])
        cards = data.get("cards", [])
        sample_cards = cards[:5]
        # Surface a flat "columns" so the existing UI can show something
        # sensible. Trello's card fields are stable across exports.
        columns = ["name", "idList", "due", "labels", "idMembers", "desc", "id"]
        return {
            "columns": columns,
            "sample_rows": [
                {k: c.get(k) for k in columns} for c in sample_cards
            ],
            "inferred_types": {c: "string" for c in columns},
            "board_name": data.get("name", ""),
            "list_count": len(lists),
            "card_count": len(cards),
        }

    def suggest_mapping(
        self, source_columns: list[str], target_entity: str
    ) -> dict[str, str]:
        # Trello is JSON — the mapping is fixed; we still return it so the
        # generic UI flow (preview / mapping confirm) has something to show.
        return {
            "name": "title",
            "idList": "status",
            "due": "due_date",
            "labels": "tags",
            "idMembers": "assignee_name",
            "desc": "description",
            "id": "external_id",
        }

    def required_fields(self, target_entity: str) -> list[str]:
        if target_entity in ("board", "cards"):
            return ["title"]
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
            data = _load_json(path)
        except Exception as exc:
            return [{"row": 0, "severity": "error", "column": None,
                     "message": f"Invalid Trello JSON: {exc}"}]
        if "cards" not in data or not isinstance(data["cards"], list):
            issues.append({"row": 0, "severity": "error", "column": "cards",
                           "message": "JSON has no 'cards' array"})
        for i, card in enumerate(data.get("cards", []), start=1):
            if not card.get("name"):
                issues.append({"row": i, "severity": "error", "column": "name",
                               "message": f"Card {i}: missing 'name'"})
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
        data = _load_json(path)
        list_map = {l["id"]: l.get("name", "") for l in data.get("lists", [])}
        out: list[dict[str, Any]] = []
        for card in data.get("cards", [])[:limit]:
            out.append({
                "title": card.get("name", ""),
                "status": status_from_section(list_map.get(card.get("idList"), "")),
                "due_date": str(parse_date(card.get("due"))) if card.get("due") else None,
                "tags": " ".join(l.get("name", "") for l in card.get("labels", [])),
                "description": card.get("desc", ""),
            })
        return out

    # ---- commit ------------------------------------------------------------

    def import_rows(self, job: ImportJob, db: Session) -> ImportJob:
        path = Path(job.source_file_path) if job.source_file_path else None
        if not path or not path.exists():
            job.status = "failed"
            return job
        data = _load_json(path)

        board_name = (job.options or {}).get("project_name") or data.get("name") or "Trello Board"
        project = get_or_create_project(db, board_name, description=data.get("desc", ""))
        imported_ids: list[list[Any]] = list(job.imported_record_ids or [])
        if not db.scalar(select(Task).where(Task.project_id == project.id)):
            imported_ids.append(["project", project.id])

        list_map = {l["id"]: l.get("name", "") for l in data.get("lists", []) if l.get("id")}
        cards = data.get("cards", [])

        # Pre-load existing markers so we can dedup across re-imports.
        existing_markers: set[str] = set()
        for existing in db.scalars(
            select(Task).where(Task.project_id == project.id)
        ):
            for token in (existing.tags or "").split():
                if token.startswith("trello:"):
                    existing_markers.add(token[len("trello:"):])

        row_no = imported = skipped = failed = 0
        seen_card_ids: set[str] = set()

        for card in cards:
            row_no += 1
            try:
                card_id = card.get("id") or ""
                title = (card.get("name") or "").strip()
                if not title:
                    self._record_error(
                        db, job, row_no, _safe_card_dict(card),
                        "missing_required_field",
                        f"Card {row_no}: missing 'name'",
                    )
                    failed += 1
                    continue
                if card_id and card_id in seen_card_ids:
                    skipped += 1
                    continue
                if card_id and card_id in existing_markers:
                    skipped += 1
                    seen_card_ids.add(card_id)
                    continue
                seen_card_ids.add(card_id)

                list_name = list_map.get(card.get("idList"), "")
                labels = card.get("labels") or []
                label_names = [l.get("name", "") for l in labels if l.get("name")]
                tags_parts: list[str] = []
                if card_id:
                    tags_parts.append(f"trello:{card_id}")
                tags_parts.extend(label_names)
                tags = " ".join(p for p in tags_parts if p)[:255]

                # Append checklists to the description body
                desc_body = card.get("desc", "") or ""
                checklists = card.get("checklists") or []
                if checklists:
                    chunks: list[str] = []
                    for cl in checklists:
                        chunks.append(f"\n\n## {cl.get('name', 'Checklist')}")
                        for item in cl.get("checkItems") or cl.get("items") or []:
                            mark = "[x]" if item.get("state") == "complete" else "[ ]"
                            chunks.append(f"- {mark} {item.get('name', '')}")
                    desc_body = (desc_body + "".join(chunks)).strip()

                task = ensure_tenant(Task(
                    project_id=project.id,
                    title=title[:180],
                    description=desc_body[:65535],
                    status=status_from_section(list_name),
                    due_date=parse_date(card.get("due")),
                    tags=tags,
                ))
                db.add(task)
                db.flush()
                imported += 1
                imported_ids.append(["task", task.id])
            except Exception as exc:  # pragma: no cover - defensive
                self._record_error(
                    db, job, row_no, _safe_card_dict(card), "unknown", str(exc)
                )
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


def _load_json(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="latin-1")
    return json.loads(text)


def _safe_card_dict(card: Any) -> dict[str, Any]:
    """Return a small representation of a card for the error log."""
    if not isinstance(card, dict):
        return {"raw": str(card)[:200]}
    return {k: card.get(k) for k in ("id", "name", "idList") if k in card}
