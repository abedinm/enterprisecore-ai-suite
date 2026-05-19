from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class SettingRead(ORMModel):
    id: str
    scope: str
    key: str
    value: str
    is_secret: bool
    updated_at: datetime


class SettingUpdate(BaseModel):
    value: str
    is_secret: bool = False


class SettingBulkUpdate(BaseModel):
    updates: dict[str, str]


class NotificationRead(ORMModel):
    id: str
    title: str
    body: str
    level: str
    link: str | None = None
    is_read: bool
    created_at: datetime


class NotificationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    body: str = ""
    level: str = "info"
    link: str | None = None
    user_id: str | None = None


class NotificationCounts(BaseModel):
    total: int
    unread: int


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=255)
    module: str | None = None
    limit: int = Field(default=25, ge=1, le=100)


class SearchHit(BaseModel):
    id: str
    module: str
    entity_type: str
    entity_id: str
    title: str
    body: str
    updated_at: datetime | None = None


class SearchResponse(BaseModel):
    items: list[SearchHit]
    total: int
    query: str


class SearchHistoryItem(ORMModel):
    id: str
    query: str
    result_count: int
    created_at: datetime
