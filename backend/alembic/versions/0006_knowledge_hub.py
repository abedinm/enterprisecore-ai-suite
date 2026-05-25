"""Knowledge Hub — KBs, documents, chunks, queries.

Adds four new tables for the local-first RAG feature. Idempotent: skips any
table that already exists so a fresh DB created by ``Base.metadata.create_all``
(which would have made the tables already) can still be stamped clean.

Revision ID: 0006_knowledge_hub
Revises: 0005_audit_detail_json
Create Date: 2026-05-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006_knowledge_hub"
down_revision: str | None = "0005_audit_detail_json"
branch_labels: str | None = None
depends_on: str | None = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def upgrade() -> None:
    if not _has_table("knowledge_bases"):
        op.create_table(
            "knowledge_bases",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("owner_id", sa.String(length=32),
                      sa.ForeignKey("users.id", ondelete="SET NULL"), index=True),
            sa.Column("name", sa.String(length=200), nullable=False, index=True),
            sa.Column("description", sa.Text),
            sa.Column("embedding_provider", sa.String(length=40),
                      server_default="ollama", nullable=False),
            sa.Column("embedding_model", sa.String(length=120),
                      server_default="nomic-embed-text", nullable=False),
            sa.Column("embedding_dim", sa.Integer, server_default="768", nullable=False),
            sa.Column("chunk_size", sa.Integer, server_default="800", nullable=False),
            sa.Column("chunk_overlap", sa.Integer, server_default="100", nullable=False),
            sa.Column("is_active", sa.Boolean, server_default=sa.text("1"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("knowledge_documents"):
        op.create_table(
            "knowledge_documents",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("kb_id", sa.String(length=32),
                      sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("name", sa.String(length=400), nullable=False, index=True),
            sa.Column("source_type", sa.String(length=20), nullable=False),
            sa.Column("source_ref", sa.String(length=2000)),
            sa.Column("storage_path", sa.String(length=2000)),
            sa.Column("mime_type", sa.String(length=120)),
            sa.Column("byte_size", sa.Integer, server_default="0", nullable=False),
            sa.Column("sha256", sa.String(length=64), index=True),
            sa.Column("status", sa.String(length=20),
                      server_default="queued", nullable=False, index=True),
            sa.Column("error_message", sa.Text),
            sa.Column("page_count", sa.Integer, server_default="0", nullable=False),
            sa.Column("char_count", sa.Integer, server_default="0", nullable=False),
            sa.Column("chunk_count", sa.Integer, server_default="0", nullable=False),
            sa.Column("ingested_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("knowledge_chunks"):
        op.create_table(
            "knowledge_chunks",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("document_id", sa.String(length=32),
                      sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("kb_id", sa.String(length=32),
                      sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("ordinal", sa.Integer, nullable=False),
            sa.Column("text", sa.Text, nullable=False),
            sa.Column("page_number", sa.Integer),
            sa.Column("char_start", sa.Integer, server_default="0", nullable=False),
            sa.Column("char_end", sa.Integer, server_default="0", nullable=False),
            sa.Column("token_count", sa.Integer, server_default="0", nullable=False),
            sa.Column("embedding", sa.LargeBinary),
            sa.Column("embedding_model", sa.String(length=120)),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("knowledge_queries"):
        op.create_table(
            "knowledge_queries",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32),
                      sa.ForeignKey("users.id", ondelete="SET NULL"), index=True),
            sa.Column("kb_ids_json", sa.Text, nullable=False),
            sa.Column("conversation_id", sa.String(length=32),
                      sa.ForeignKey("ai_conversations.id", ondelete="SET NULL")),
            sa.Column("question", sa.Text, nullable=False),
            sa.Column("retrieved_chunk_ids_json", sa.Text, nullable=False),
            sa.Column("answer", sa.Text),
            sa.Column("provider", sa.String(length=40)),
            sa.Column("model", sa.String(length=120)),
            sa.Column("latency_ms", sa.Integer, server_default="0", nullable=False),
            sa.Column("tokens_in", sa.Integer, server_default="0", nullable=False),
            sa.Column("tokens_out", sa.Integer, server_default="0", nullable=False),
            sa.Column("cost_usd", sa.Numeric(12, 6), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    for tbl in ("knowledge_queries", "knowledge_chunks",
                "knowledge_documents", "knowledge_bases"):
        if _has_table(tbl):
            op.drop_table(tbl)
