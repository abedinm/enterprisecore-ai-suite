"""Pydantic schemas for the background-job admin endpoints."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel, Timestamped


class JobOut(Timestamped):
    function_name: str
    args_json: dict
    status: str
    queue_name: str
    attempts: int
    last_error: str | None = None
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result_excerpt: str | None = None
    rq_job_id: str | None = None
    created_by_id: str | None = None


class JobAttemptOut(Timestamped):
    job_id: str
    attempt_number: int
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error_message: str | None = None


class JobDetailOut(JobOut):
    """Job with its attempt history attached, for the detail endpoint."""

    attempts_history: list[JobAttemptOut] = []


class JobStatsOut(BaseModel):
    queued: int
    running: int
    completed_today: int
    failed_today: int
    cancelled_today: int
    total: int


class JobActionOut(BaseModel):
    job_id: str
    status: str
    message: str | None = None
