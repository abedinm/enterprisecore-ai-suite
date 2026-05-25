from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from sqlalchemy import UniqueConstraint

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class Document(IdMixin, TenantMixin, TimestampMixin, Base):
    title: Mapped[str] = mapped_column(String(220), index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str | None] = mapped_column(String(500))
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    visibility: Mapped[str] = mapped_column(String(40), default="private")


class DocumentVersion(IdMixin, TenantMixin, TimestampMixin, Base):
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, default="")
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class DocumentTag(IdMixin, TenantMixin, TimestampMixin, Base):
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    tag: Mapped[str] = mapped_column(String(80), index=True)


class DocumentShare(IdMixin, TenantMixin, TimestampMixin, Base):
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    permission: Mapped[str] = mapped_column(String(30), default="read")


class ESignature(IdMixin, TenantMixin, TimestampMixin, Base):
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    signer_name: Mapped[str] = mapped_column(String(180))
    signer_email: Mapped[str | None] = mapped_column(String(255))
    signature_hash: Mapped[str] = mapped_column(String(255))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)


class DocumentTemplate(IdMixin, TenantMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str | None] = mapped_column(String(120))
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_document_templates_tenant_name"),)
