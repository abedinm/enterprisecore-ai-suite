from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class MessageThread(IdMixin, TimestampMixin, Base):
    title: Mapped[str] = mapped_column(String(180), index=True)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Message(IdMixin, TimestampMixin, Base):
    thread_id: Mapped[str] = mapped_column(ForeignKey("message_threads.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Announcement(IdMixin, TimestampMixin, Base):
    title: Mapped[str] = mapped_column(String(180), index=True)
    body: Mapped[str] = mapped_column(Text)
    audience: Mapped[str] = mapped_column(String(80), default="all")
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)


class CalendarEvent(IdMixin, TimestampMixin, Base):
    title: Mapped[str] = mapped_column(String(180), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(255))
    meeting_url: Mapped[str | None] = mapped_column(String(500))


class SharedNote(IdMixin, TimestampMixin, Base):
    title: Mapped[str] = mapped_column(String(180), index=True)
    body: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Poll(IdMixin, TimestampMixin, Base):
    question: Mapped[str] = mapped_column(String(255))
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PollOption(IdMixin, TimestampMixin, Base):
    poll_id: Mapped[str] = mapped_column(ForeignKey("polls.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(180))


class PollVote(IdMixin, TimestampMixin, Base):
    poll_option_id: Mapped[str] = mapped_column(ForeignKey("poll_options.id", ondelete="CASCADE"))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


class Feedback(IdMixin, TimestampMixin, Base):
    subject: Mapped[str] = mapped_column(String(200), default="")
    category: Mapped[str] = mapped_column(String(40), default="general", index=True)
    source: Mapped[str] = mapped_column(String(80), default="internal")
    rating: Mapped[int] = mapped_column(default=0)
    body: Mapped[str] = mapped_column(Text, default="")
    sentiment: Mapped[str | None] = mapped_column(String(40))


class WikiPage(IdMixin, TimestampMixin, Base):
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(220), index=True)
    body: Mapped[str] = mapped_column(Text, default="")
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("wiki_pages.id", ondelete="SET NULL"), nullable=True)
