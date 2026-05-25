"""Schemas for timetable slots."""
from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class SlotCreate(BaseModel):
    class_id: str
    room_id: str
    semester_id: str
    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def _start_before_end(self):
        # Reject zero-length / inverted slots at the schema boundary so the
        # service layer never has to second-guess the input shape.
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be earlier than end_time")
        return self


class SlotUpdate(BaseModel):
    class_id: str | None = None
    room_id: str | None = None
    semester_id: str | None = None
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None


class SlotOut(ORMModel):
    id: str
    class_id: str
    room_id: str
    semester_id: str
    day_of_week: int
    start_time: time
    end_time: time
    created_at: datetime
    updated_at: datetime
