from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class CodeProject(IdMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(180), index=True)
    root_path: Mapped[str] = mapped_column(String(500))
    language: Mapped[str | None] = mapped_column(String(80))
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class CodeSnippet(IdMixin, TimestampMixin, Base):
    title: Mapped[str] = mapped_column(String(180), index=True)
    language: Mapped[str] = mapped_column(String(80), index=True)
    code: Mapped[str] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(Text, default="[]")
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class ApiRequest(IdMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(180), index=True)
    method: Mapped[str] = mapped_column(String(12), default="GET")
    url: Mapped[str] = mapped_column(String(1000))
    headers: Mapped[str] = mapped_column(Text, default="{}")
    body: Mapped[str] = mapped_column(Text, default="")


class GitRepo(IdMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(180), index=True)
    path: Mapped[str] = mapped_column(String(500), unique=True)
    remote_url: Mapped[str | None] = mapped_column(String(500))
    default_branch: Mapped[str] = mapped_column(String(120), default="main")
