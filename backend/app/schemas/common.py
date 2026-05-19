from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    message: str


class PaginatedResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int


class Timestamped(ORMModel):
    id: str
    created_at: datetime
    updated_at: datetime
