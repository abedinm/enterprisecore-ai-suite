"""Importer ABC + shared helpers.

Every concrete importer follows the same lifecycle:

1. ``detect_schema(file_path)`` — read the header + a few rows, infer types.
2. ``suggest_mapping(source_columns, target_entity)`` — heuristic guess of
   ``{source_col -> ec_field}`` so the customer doesn't start from blank.
3. ``validate(job, db)`` — dry-run all rows, collect issues without
   touching the database (no inserts).
4. ``preview(job, db, limit)`` — show the first N rows as they'd land,
   fully mapped + transformed.
5. ``import_rows(job, db)`` — actually persist, recording every created
   row id on the job for later rollback.
6. ``rollback(job, db)`` — undo a previous ``import_rows`` by deleting
   exactly the rows it created (no collateral damage).
"""
from __future__ import annotations

import csv
import io
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.import_jobs import ImportError, ImportJob


# Hard cap on rows we'll iterate per importer — protects the synchronous
# commit endpoint from a runaway 10M-row upload. The task spec recommends
# 100K, we leave headroom but stop catastrophically large files.
MAX_ROWS_PER_FILE = 200_000


class Importer(ABC):
    """Abstract base every concrete importer must implement."""

    source: str = ""
    supported_entities: list[str] = []
    description: str = ""

    # ---- subclass contract -------------------------------------------------

    @abstractmethod
    def suggest_mapping(self, source_columns: list[str], target_entity: str) -> dict[str, str]:
        """Heuristic source-col → EC-field mapping for the given target."""

    @abstractmethod
    def import_rows(self, job: ImportJob, db: Session) -> ImportJob:
        """Actually persist rows. Mutates ``job`` in-place and returns it."""

    # ---- shared default behaviour subclasses can lean on -------------------

    def detect_schema(self, file_path: Path) -> dict[str, Any]:
        """Read the CSV header + first ~5 rows, return inferred types."""
        rows = self._iter_rows(file_path, limit=5)
        sample = list(rows)
        columns = list(sample[0].keys()) if sample else []
        inferred = {col: _infer_type(sample, col) for col in columns}
        return {
            "columns": columns,
            "sample_rows": sample,
            "inferred_types": inferred,
        }

    def validate(self, job: ImportJob, db: Session) -> list[dict[str, Any]]:
        """Default validator: walk rows, check required EC fields are mapped+present."""
        issues: list[dict[str, Any]] = []
        required = self.required_fields(job.target_entity)
        mapping = job.column_mapping or {}
        mapped_ec_fields = set(mapping.values())
        for field in required:
            if field not in mapped_ec_fields:
                issues.append({
                    "row": 0,
                    "severity": "error",
                    "column": None,
                    "message": f"Required field '{field}' is not mapped to any source column",
                })

        # Walk the data rows and check required fields actually have values.
        if job.source_file_path:
            path = Path(job.source_file_path)
            if path.exists():
                row_no = 0
                for raw in self._iter_rows(path):
                    row_no += 1
                    mapped = _apply_mapping(raw, mapping)
                    for field in required:
                        if field not in mapped or mapped[field] in (None, ""):
                            issues.append({
                                "row": row_no,
                                "severity": "error",
                                "column": field,
                                "message": f"Row {row_no}: required field '{field}' is empty",
                            })
                    if row_no >= MAX_ROWS_PER_FILE:
                        issues.append({
                            "row": row_no,
                            "severity": "warning",
                            "column": None,
                            "message": f"File exceeds {MAX_ROWS_PER_FILE} rows; stopped validating",
                        })
                        break
        return issues

    def preview(self, job: ImportJob, db: Session, limit: int = 10) -> list[dict[str, Any]]:
        """Apply mapping to the first ``limit`` rows and show what would land."""
        if not job.source_file_path:
            return []
        path = Path(job.source_file_path)
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        for raw in self._iter_rows(path, limit=limit):
            out.append(_apply_mapping(raw, job.column_mapping or {}))
        return out

    def rollback(self, job: ImportJob, db: Session) -> None:
        """Default rollback: delete every row tracked in imported_record_ids.

        ``imported_record_ids`` is a list of ``[entity, id]`` pairs.
        """
        if not job.imported_record_ids:
            return
        from app.models import crm as crm_models, finance as finance_models, hr as hr_models

        entity_to_model = {
            "contact": crm_models.Contact,
            "deal": crm_models.Deal,
            "customer": finance_models.Customer,
            "vendor": finance_models.Vendor,
            "invoice": finance_models.Invoice,
            "expense": finance_models.Expense,
            "employee": hr_models.Employee,
        }
        for entry in job.imported_record_ids:
            try:
                entity, pk = entry
            except (ValueError, TypeError):
                continue
            model = entity_to_model.get(entity)
            if not model:
                continue
            obj = db.get(model, pk)
            if obj is not None:
                db.delete(obj)
        job.imported_record_ids = []
        job.status = "rolled_back"
        db.flush()

    # ---- hooks subclasses can override -------------------------------------

    def required_fields(self, target_entity: str) -> list[str]:
        """EC field names that must be present for ``target_entity``."""
        return []

    # ---- shared utility helpers --------------------------------------------

    def _iter_rows(self, file_path: Path, limit: int | None = None) -> Iterable[dict[str, str]]:
        """Yield rows as dicts. Tolerates BOM + variable line endings."""
        try:
            text = file_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = file_path.read_text(encoding="latin-1")
        reader = csv.DictReader(io.StringIO(text))
        for i, row in enumerate(reader):
            if limit is not None and i >= limit:
                return
            yield {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k is not None}

    def _record_error(
        self,
        db: Session,
        job: ImportJob,
        row_number: int,
        source_data: dict[str, Any],
        error_type: str,
        message: str,
    ) -> None:
        err = ImportError(
            import_job_id=job.id,
            row_number=row_number,
            source_data=source_data,
            error_type=error_type,
            error_message=message,
        )
        db.add(err)


# ---------------------------------------------------------------------------
# module-level helpers
# ---------------------------------------------------------------------------

def _apply_mapping(raw: dict[str, str], mapping: dict[str, str]) -> dict[str, Any]:
    """Translate a source row through ``{source_col: ec_field}``.

    Multi-source-col → single EC-field combinations (e.g. "First Name" +
    "Last Name" → name) are handled by special-cased fields with a `+` in
    the source value, the importer composes them upstream when needed.
    """
    out: dict[str, Any] = {}
    for src_col, ec_field in mapping.items():
        if ec_field in (None, "", "__skip__"):
            continue
        val = raw.get(src_col)
        if val in (None, ""):
            continue
        # Merge multiple source columns mapped to the same EC field with a space.
        if ec_field in out and isinstance(out[ec_field], str) and isinstance(val, str):
            out[ec_field] = (out[ec_field] + " " + val).strip()
        else:
            out[ec_field] = val
    return out


def _infer_type(rows: list[dict[str, Any]], col: str) -> str:
    """Tiny best-effort type sniff: int / float / date / string."""
    saw_int = saw_float = saw_date = saw_str = False
    for r in rows:
        v = r.get(col)
        if v in (None, ""):
            continue
        if isinstance(v, str):
            stripped = v.strip()
            if stripped.replace("-", "").isdigit():
                saw_int = True
                continue
            try:
                float(stripped)
                saw_float = True
                continue
            except ValueError:
                pass
            # Crude date sniff: 4-digit-year prefix or slash-separated
            if (len(stripped) >= 8 and (stripped[4] in "-/" or stripped[2] in "-/")):
                saw_date = True
                continue
            saw_str = True
    if saw_str:
        return "string"
    if saw_date:
        return "date"
    if saw_float:
        return "float"
    if saw_int:
        return "int"
    return "string"
