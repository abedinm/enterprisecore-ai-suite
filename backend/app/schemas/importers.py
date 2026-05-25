"""Pydantic schemas for the data-migration importer surface."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ImportJobOut(ORMModel):
    id: str
    source: str
    target_module: str
    target_entity: str
    status: str
    source_file_path: str | None
    column_mapping: dict[str, Any]
    row_count_total: int
    row_count_imported: int
    row_count_skipped: int
    row_count_failed: int
    started_by_id: str | None
    completed_at: datetime | None
    config: dict[str, Any]
    options: dict[str, Any]
    can_rollback: bool
    created_at: datetime
    updated_at: datetime


class ImportJobCreateOut(ImportJobOut):
    """Returned by the multipart upload endpoint."""


class MappingUpdateIn(BaseModel):
    column_mapping: dict[str, str] = Field(default_factory=dict)
    options: dict[str, Any] | None = None


class DetectSchemaOut(BaseModel):
    columns: list[str]
    sample_rows: list[dict[str, Any]]
    inferred_types: dict[str, str]


class SuggestMappingOut(BaseModel):
    mapping: dict[str, str]
    unmapped_columns: list[str]
    target_fields: list[str]


class ValidationIssue(BaseModel):
    row: int
    severity: str  # "error" | "warning"
    column: str | None = None
    message: str


class ValidationOut(BaseModel):
    issues: list[ValidationIssue]
    error_count: int
    warning_count: int
    row_count: int


class PreviewOut(BaseModel):
    rows: list[dict[str, Any]]
    column_mapping: dict[str, str]


class ImporterInfo(BaseModel):
    source: str
    supported_entities: list[str]
    description: str


class ImporterListOut(BaseModel):
    importers: list[ImporterInfo]


class ImportErrorOut(ORMModel):
    id: str
    import_job_id: str
    row_number: int
    source_data: dict[str, Any]
    error_type: str
    error_message: str
    created_at: datetime
