"""Generic CSV importer.

No source-specific knowledge — the user provides a manual mapping and we
pass the rows through to the right EC model. Used as the universal fallback
for any source we don't have a dedicated importer for.

Also the workhorse the HubSpot / Salesforce / QuickBooks importers
delegate the actual commit to: they only override ``suggest_mapping`` and
add source-specific synonyms, the row-level INSERT logic lives here.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crm import Contact, Deal
from app.models.finance import Customer, Expense, Invoice, Vendor
from app.models.hr import Employee
from app.models.import_jobs import ImportJob
from app.services.importers import column_mapping
from app.services.importers.base import MAX_ROWS_PER_FILE, Importer, _apply_mapping


# Target entity -> (ORM model, required EC fields, name field for audit)
ENTITY_TARGETS: dict[str, dict[str, Any]] = {
    "contact": {"model": Contact, "required": ["name"], "name_field": "name", "entity_key": "contact"},
    "customer": {"model": Customer, "required": ["name"], "name_field": "name", "entity_key": "customer"},
    "vendor": {"model": Vendor, "required": ["name"], "name_field": "name", "entity_key": "vendor"},
    "deal": {"model": Deal, "required": ["title"], "name_field": "title", "entity_key": "deal"},
    "invoice": {"model": Invoice, "required": ["invoice_number", "issue_date", "due_date"], "name_field": "invoice_number", "entity_key": "invoice"},
    "expense": {"model": Expense, "required": ["date", "amount"], "name_field": "description", "entity_key": "expense"},
    "employee": {"model": Employee, "required": ["full_name", "employee_code"], "name_field": "full_name", "entity_key": "employee"},
}


def _coerce(field: str, value: Any) -> Any:
    """Coerce a raw CSV string to the right Python type for the EC field."""
    if value in (None, ""):
        return None
    s = str(value).strip()

    # money / numeric
    if field in {"value", "amount", "total", "subtotal", "tax_total", "discount_total",
                 "probability", "salary"}:
        try:
            cleaned = s.replace(",", "").replace("$", "").replace("£", "").replace("€", "")
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None

    # dates
    if field in {"expected_close_date", "issue_date", "due_date", "date", "hire_date"}:
        return _parse_date(s)

    # ints
    if field in {"score"}:
        try:
            return int(s)
        except ValueError:
            return None

    # currency code
    if field == "currency":
        return s.upper()[:3] or "USD"

    return s


def _parse_date(s: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def _find_existing(db: Session, model, mapped: dict[str, Any], strategy: str) -> Any | None:
    """Look up an existing row using the dedup strategy."""
    if strategy == "by_email" and mapped.get("email"):
        return db.scalar(select(model).where(model.email == mapped["email"]))
    if strategy == "by_name" and mapped.get("name"):
        return db.scalar(select(model).where(model.name == mapped["name"]))
    if strategy == "by_invoice_number" and mapped.get("invoice_number"):
        return db.scalar(select(model).where(model.invoice_number == mapped["invoice_number"]))
    if strategy == "by_employee_code" and mapped.get("employee_code"):
        return db.scalar(select(model).where(model.employee_code == mapped["employee_code"]))
    return None


class CsvGenericImporter(Importer):
    """Generic CSV importer with user-supplied column mapping."""

    source = "csv"
    supported_entities = list(ENTITY_TARGETS.keys())
    description = "Generic CSV import with manual column mapping"

    # ---- Importer contract -------------------------------------------------

    def suggest_mapping(self, source_columns: list[str], target_entity: str) -> dict[str, str]:
        return column_mapping.suggest(source_columns, target_entity)

    def required_fields(self, target_entity: str) -> list[str]:
        target = ENTITY_TARGETS.get(target_entity)
        if not target:
            return []
        return list(target["required"])

    def import_rows(self, job: ImportJob, db: Session) -> ImportJob:
        target = ENTITY_TARGETS.get(job.target_entity)
        if not target:
            job.status = "failed"
            return job
        model = target["model"]
        entity_key = target["entity_key"]
        required = target["required"]
        options = job.options or {}
        on_conflict = options.get("on_conflict", "skip")
        dedup_strategy = options.get("dedup_strategy")

        path = Path(job.source_file_path) if job.source_file_path else None
        if not path or not path.exists():
            job.status = "failed"
            return job

        mapping = job.column_mapping or {}
        row_no = 0
        imported = skipped = failed = 0
        imported_ids: list[list[str]] = list(job.imported_record_ids or [])
        seen_dedup_keys: set[str] = set()

        for raw in self._iter_rows(path):
            row_no += 1
            if row_no > MAX_ROWS_PER_FILE:
                self._record_error(
                    db, job, row_no, raw, "unknown",
                    f"Stopped at row {row_no}: exceeds {MAX_ROWS_PER_FILE} row safety cap",
                )
                failed += 1
                break
            try:
                mapped = _apply_mapping(raw, mapping)
                # Compose first_name + last_name → name if both present and name isn't
                if "name" not in mapped:
                    first = mapped.pop("first_name", None)
                    last = mapped.pop("last_name", None)
                    composite = " ".join(p for p in (first, last) if p)
                    if composite:
                        mapped["name"] = composite

                # Special: deal "contact_name" should resolve to contact_id
                if entity_key == "deal" and "contact_name" in mapped:
                    contact_name = mapped.pop("contact_name")
                    existing = db.scalar(select(Contact).where(Contact.name == contact_name))
                    if existing:
                        mapped["contact_id"] = existing.id

                # Coerce types
                typed = {k: _coerce(k, v) for k, v in mapped.items()}
                typed = {k: v for k, v in typed.items() if v is not None}

                # Required-field gate
                missing = [f for f in required if not typed.get(f)]
                if missing:
                    self._record_error(
                        db, job, row_no, raw, "missing_required_field",
                        f"Row {row_no}: missing required field(s): {', '.join(missing)}",
                    )
                    failed += 1
                    continue

                # Dedup within the same file
                if dedup_strategy:
                    key = self._dedup_key(typed, dedup_strategy)
                    if key:
                        if key in seen_dedup_keys:
                            skipped += 1
                            continue
                        seen_dedup_keys.add(key)

                # Dedup against DB
                existing = _find_existing(db, model, typed, dedup_strategy) if dedup_strategy else None
                if existing is not None:
                    if on_conflict == "skip":
                        skipped += 1
                        continue
                    if on_conflict == "update":
                        for k, v in typed.items():
                            if hasattr(existing, k):
                                setattr(existing, k, v)
                        db.flush()
                        imported += 1
                        imported_ids.append([entity_key, existing.id])
                        continue
                    # "create_duplicate" -> fall through to INSERT

                # Filter to columns the model actually has
                valid_attrs = {k: v for k, v in typed.items() if hasattr(model, k)}
                obj = model(**valid_attrs)
                db.add(obj)
                db.flush()
                imported += 1
                imported_ids.append([entity_key, obj.id])
            except Exception as exc:  # pragma: no cover - defensive
                self._record_error(db, job, row_no, raw, "unknown", str(exc))
                failed += 1

        job.row_count_total = row_no
        job.row_count_imported = imported
        job.row_count_skipped = skipped
        job.row_count_failed = failed
        job.imported_record_ids = imported_ids
        job.status = "completed" if failed == 0 else "completed"
        job.completed_at = datetime.now()
        db.flush()
        return job

    def _dedup_key(self, mapped: dict[str, Any], strategy: str) -> str | None:
        if strategy == "by_email":
            return (mapped.get("email") or "").lower() or None
        if strategy == "by_name":
            return (mapped.get("name") or "").lower() or None
        if strategy == "by_invoice_number":
            return mapped.get("invoice_number") or None
        if strategy == "by_employee_code":
            return mapped.get("employee_code") or None
        return None
