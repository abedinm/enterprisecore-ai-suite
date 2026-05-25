"""SQLAlchemy models for the Knowledge Hub (RAG over local documents)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, LargeBinary,
                        Numeric, String, Text, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class KnowledgeBase(IdMixin, TenantMixin, TimestampMixin, Base):
    """A Knowledge Base is a named collection of documents that share the
    same embedding model and chunking parameters. Users query across one or
    more KBs at retrieval time."""

    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    embedding_provider: Mapped[str] = mapped_column(
        String(40), default="ollama", nullable=False
    )
    embedding_model: Mapped[str] = mapped_column(
        String(120), default="nomic-embed-text", nullable=False
    )
    embedding_dim: Mapped[int] = mapped_column(Integer, default=768, nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, default=800, nullable=False)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class KnowledgeDocument(IdMixin, TenantMixin, TimestampMixin, Base):
    """A single source document inside a KB. Goes through queued → parsing →
    embedding → ready (or failed). The original blob is kept on disk; an
    extracted text cache lives next to it so re-embed skips the parse step."""

    kb_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(400), index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(2000))
    storage_path: Mapped[str | None] = mapped_column(String(2000))
    mime_type: Mapped[str | None] = mapped_column(String(120))
    byte_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(
        String(20), default="queued", nullable=False, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeChunk(IdMixin, TenantMixin, Base):
    """One vector-indexed slice of a document. Embedding stored as raw
    float32 bytes in a LargeBinary column — small enough to query in batch
    via numpy without a dedicated vector DB."""

    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    kb_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    char_start: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class KnowledgeQuery(IdMixin, TenantMixin, TimestampMixin, Base):
    """Audit trail for every RAG retrieval. Lets us inspect which chunks the
    LLM was shown for any historical answer."""

    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    kb_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="SET NULL")
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_chunk_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(120))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0"), nullable=False
    )
