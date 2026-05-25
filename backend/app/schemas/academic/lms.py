"""Schemas for LMS library resources."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


ResourceType = Literal[
    "note", "slide", "past_exam", "book_link", "youtube", "lab_report",
]


class LmsResourceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    department: str = ""
    semester: str = ""
    course_code: str = ""
    resource_type: ResourceType
    file_path: str | None = None
    url: str | None = None

    @model_validator(mode="after")
    def _must_have_source(self):
        # Resource is useless without somewhere to point at; reject early.
        if not (self.file_path or self.url):
            raise ValueError("either file_path or url must be set")
        return self


class LmsResourceUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    department: str | None = None
    semester: str | None = None
    course_code: str | None = None
    resource_type: ResourceType | None = None
    file_path: str | None = None
    url: str | None = None


class LmsResourceOut(ORMModel):
    id: str
    title: str
    description: str
    department: str
    semester: str
    course_code: str
    resource_type: str
    file_path: str | None
    url: str | None
    uploaded_by_id: str | None
    download_count: int
    created_at: datetime
    updated_at: datetime


class LmsDownloadOut(BaseModel):
    """Response from POST /lms/resources/{id}/download — the URL the caller
    should redirect to or stream from, plus the new counter for UI updates."""

    resource_id: str
    file_path: str | None = None
    url: str | None = None
    download_count: int
