"""Pydantic schemas for the workflow + integration endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ORMModel, Timestamped


# ---- Workflows ------------------------------------------------------------

class WorkflowActionIn(BaseModel):
    type: str = Field(..., min_length=1, max_length=60)
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=180)
    description: str | None = None
    is_active: bool = True
    trigger_event_type: str = Field(..., min_length=1, max_length=120)
    trigger_filter: dict[str, Any] = Field(default_factory=dict)
    actions: list[WorkflowActionIn] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    trigger_event_type: str | None = None
    trigger_filter: dict[str, Any] | None = None
    actions: list[WorkflowActionIn] | None = None


class WorkflowOut(Timestamped):
    name: str
    description: str | None = None
    is_active: bool
    trigger_event_type: str
    trigger_filter: dict[str, Any]
    actions: list[dict[str, Any]]
    last_run_at: datetime | None = None
    runs_count: int
    failures_count: int
    created_by_id: str | None = None


class WorkflowRunOut(Timestamped):
    workflow_id: str
    event_id: str
    event_type: str
    event_payload: dict[str, Any]
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    action_results: list[dict[str, Any]]


class WorkflowActionTypeInfo(BaseModel):
    type: str
    description: str
    config_schema: dict[str, Any]


# ---- Integrations ---------------------------------------------------------

class IntegrationCatalogEntry(BaseModel):
    key: str
    name: str
    category: str
    description: str
    configurable: bool
    default_event_types: list[str]


class TenantIntegrationOut(Timestamped):
    key: str
    name: str
    is_enabled: bool
    config: dict[str, Any]
    installed_by_user_id: str | None = None
    installed_at: datetime | None = None
    last_used_at: datetime | None = None


class IntegrationInstallResponse(BaseModel):
    key: str
    install_url: str | None = None
    api_key: str | None = None
    requires_oauth: bool = True


class IntegrationConfigUpdate(BaseModel):
    config: dict[str, Any]
    is_enabled: bool | None = None
