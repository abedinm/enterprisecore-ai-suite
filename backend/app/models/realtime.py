"""Realtime / collaborative-editing persistence.

One table — ``yjs_documents`` — that snapshots the canonical state of a
Yjs collaborative document so newly-joining clients can sync from disk
rather than having to be told the state by another connected peer.

The ``update_log`` column is the CRDT update stream: bytes appended to it
can be replayed in order against a fresh Y.Doc to reconstruct the live
state. ``state_vector`` is the compact "where are we" pointer that lets a
joiner ask for everything they've missed without re-downloading the
whole history. Both are opaque to the server when running in
scaffold-only mode (no ``y-py``); the room manager just stores the
client-sent bytes.

A document is tenant-scoped through ``TenantMixin`` so the ORM auto-
filter prevents tenant A from ever opening tenant B's room.
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class YjsDocument(IdMixin, TenantMixin, TimestampMixin, Base):
    """Persisted Yjs document state for a single collaborative document.

    ``document_id`` references the row in the Documents-module table that
    backs this collaborative surface. ``document_kind`` lets the same
    table serve multiple modules ("doc" for Documents, "wiki" for the
    knowledge base, "marketing-post" for editable marketing copy, etc.)
    without needing a polymorphic FK.
    """

    __tablename__ = "yjs_documents"

    document_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    document_kind: Mapped[str] = mapped_column(String(40), default="doc", nullable=False)
    state_vector: Mapped[bytes | None] = mapped_column(LargeBinary)
    update_log: Mapped[bytes | None] = mapped_column(LargeBinary)
    last_modified_by_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    active_user_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
