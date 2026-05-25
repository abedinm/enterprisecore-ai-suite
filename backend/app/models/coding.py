"""SQLAlchemy models for the AI Coding Assistant module."""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from sqlalchemy import UniqueConstraint

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class CodeProject(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "code_projects"

    name: Mapped[str] = mapped_column(String(200), index=True)
    path: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    language_primary: Mapped[str | None] = mapped_column(String(40))
    is_git: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)


class CodeSnippet(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "code_snippets"

    title: Mapped[str] = mapped_column(String(200), index=True)
    language: Mapped[str] = mapped_column(String(40), index=True, default="text")
    code: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)


class ApiRequest(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "api_requests"

    name: Mapped[str] = mapped_column(String(200), index=True)
    method: Mapped[str] = mapped_column(String(12), default="GET", nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    headers: Mapped[dict] = mapped_column(JSON, default=dict)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    body: Mapped[str | None] = mapped_column(Text)
    collection: Mapped[str | None] = mapped_column(String(120), index=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)


class GitRepo(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "git_repos"

    name: Mapped[str] = mapped_column(String(200), index=True)
    path: Mapped[str] = mapped_column(String(500))
    remote_url: Mapped[str | None] = mapped_column(String(500))
    default_branch: Mapped[str] = mapped_column(String(120), default="main")
    __table_args__ = (UniqueConstraint("tenant_id", "path", name="uq_git_repos_tenant_path"),)


class RegexLibraryEntry(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "regex_library_entries"

    title: Mapped[str] = mapped_column(String(200), index=True)
    pattern: Mapped[str] = mapped_column(Text)
    flags: Mapped[str] = mapped_column(String(20), default="")
    description: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)


class DatabaseConnection(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "database_connections"

    name: Mapped[str] = mapped_column(String(200), index=True)
    dialect: Mapped[str] = mapped_column(String(40), nullable=False)
    dsn_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
