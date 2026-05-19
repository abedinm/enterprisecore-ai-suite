"""Communication module schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class MessageThreadIn(BaseModel):
    title: str | None = None
    participants: list[str] = []  # user IDs


class MessageThreadOut(ORMModel):
    id: str
    title: str | None
    created_at: datetime


class MessageIn(BaseModel):
    thread_id: str
    body: str = Field(min_length=1)


class MessageOut(ORMModel):
    id: str
    thread_id: str
    sender_id: str
    body: str
    created_at: datetime


class AnnouncementIn(BaseModel):
    title: str = Field(min_length=1)
    body: str = ""
    audience: str = "all"


class AnnouncementOut(ORMModel):
    id: str
    title: str
    body: str
    audience: str
    created_at: datetime


class CalendarEventIn(BaseModel):
    title: str
    starts_at: datetime
    ends_at: datetime
    location: str | None = None
    meeting_url: str | None = None
    attendees: list[str] = []  # emails


class CalendarEventOut(ORMModel):
    id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    location: str | None
    meeting_url: str | None


class SharedNoteIn(BaseModel):
    title: str
    body: str = ""


class SharedNoteOut(ORMModel):
    id: str
    title: str
    body: str
    created_at: datetime
    updated_at: datetime


class PollIn(BaseModel):
    question: str
    options: list[str]
    closes_at: datetime | None = None
    multi_choice: bool = False


class PollOut(ORMModel):
    id: str
    question: str
    multi_choice: bool
    closes_at: datetime | None
    options: list[dict]
    total_votes: int


class PollVoteIn(BaseModel):
    poll_id: str
    option_ids: list[str]


class FeedbackIn(BaseModel):
    subject: str
    body: str
    category: str = "general"


class FeedbackOut(ORMModel):
    id: str
    subject: str
    body: str
    category: str
    created_at: datetime


class WikiPageIn(BaseModel):
    title: str
    body: str = ""
    parent_id: str | None = None


class WikiPageOut(ORMModel):
    id: str
    title: str
    body: str
    parent_id: str | None
    created_at: datetime
    updated_at: datetime
