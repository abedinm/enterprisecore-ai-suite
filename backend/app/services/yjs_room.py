"""In-memory Yjs room manager — scaffold persistence layer.

Each (tenant_id, document_id) keys a ``_RoomState`` that tracks:

* The current snapshot blob (concatenated update log from disk + any
  updates received since the last persist).
* A "dirty" flag and the timestamp of the last successful persist so the
  debounced persister knows when to write to the ``yjs_documents``
  table.
* A reference count of active joiners — when it hits zero we flush and
  drop the room from memory.

Without ``y-py`` we can't compress the update log into a state vector
or garbage-collect stale tombstones, so the snapshot grows linearly
with edits. For v1 that's acceptable: the canonical Yjs client merges
incoming updates idempotently, and operators can run a periodic
re-snapshot job once a real Yjs CRDT is wired in.

All DB writes go through the tenant filter bypass because the room
manager is invoked from inside the WebSocket handler which has no HTTP
request scope; the tenant_id is carried explicitly through the API
and used for ORM filtering.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.db.session import SessionLocal
from app.models.realtime import YjsDocument

logger = logging.getLogger(__name__)

# How long to wait between persist passes for a dirty room (seconds).
PERSIST_DEBOUNCE_SECONDS = 10.0


@dataclass
class _RoomState:
    tenant_id: str
    document_id: str
    snapshot: bytearray = field(default_factory=bytearray)
    dirty: bool = False
    last_persist_at: float = field(default_factory=time.time)
    user_count: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


_rooms: dict[tuple[str, str], _RoomState] = {}
_rooms_lock = threading.Lock()


def _get_or_load(tenant_id: str, document_id: str) -> _RoomState:
    """Look up the in-memory room, hydrating from the DB on first touch."""
    key = (tenant_id, document_id)
    with _rooms_lock:
        room = _rooms.get(key)
        if room is not None:
            return room
        room = _RoomState(tenant_id=tenant_id, document_id=document_id)
        _rooms[key] = room

    # Hydrate from DB outside the global lock so a slow query doesn't
    # block every other room.
    with SessionLocal() as db, tenant_scope(tenant_id):
        from sqlalchemy import select

        row = db.scalar(
            select(YjsDocument).where(
                YjsDocument.document_id == document_id
            )
        )
        if row and row.update_log:
            with room.lock:
                room.snapshot = bytearray(row.update_log)
    return room


def join_room(*, tenant_id: str, document_id: str, user_id: str) -> bytes:
    """Mark a user as joined to the room and return the current snapshot.

    Returns an empty bytes object if there is no persisted state yet —
    fresh document. The caller (the WS handler) should send the returned
    bytes back to the joining client so it can ``Y.applyUpdate(...)``
    them into its local doc.
    """
    room = _get_or_load(tenant_id, document_id)
    with room.lock:
        room.user_count += 1
        snapshot = bytes(room.snapshot)
    _update_active_count(tenant_id, document_id, delta=+1, user_id=user_id)
    return snapshot


def leave_room(*, tenant_id: str, document_id: str, user_id: str) -> None:
    """Decrement the room's active-user count + force a final persist when
    it reaches zero so the next joiner starts from a fully-flushed state.
    """
    key = (tenant_id, document_id)
    with _rooms_lock:
        room = _rooms.get(key)
    if room is None:
        return
    final = False
    with room.lock:
        room.user_count = max(0, room.user_count - 1)
        if room.user_count == 0:
            final = True
    if final:
        _persist(room, force=True)
        with _rooms_lock:
            _rooms.pop(key, None)
    _update_active_count(tenant_id, document_id, delta=-1, user_id=user_id)


def ingest_update(
    *,
    tenant_id: str,
    document_id: str,
    update_bytes: bytes,
    user_id: str | None = None,
) -> None:
    """Append a CRDT update to the room snapshot + persist if debounce fired."""
    if not update_bytes:
        return
    room = _get_or_load(tenant_id, document_id)
    needs_persist = False
    with room.lock:
        room.snapshot.extend(update_bytes)
        room.dirty = True
        if (time.time() - room.last_persist_at) >= PERSIST_DEBOUNCE_SECONDS:
            needs_persist = True
    if needs_persist:
        _persist(room, user_id=user_id)


def _persist(room: _RoomState, *, force: bool = False, user_id: str | None = None) -> None:
    """Write the current snapshot to ``yjs_documents``.

    Idempotent — if the row doesn't exist we INSERT it; otherwise UPDATE.
    ``force=True`` writes even if not dirty (used on final disconnect).
    """
    with room.lock:
        if not room.dirty and not force:
            return
        snapshot = bytes(room.snapshot)
        room.last_persist_at = time.time()
        room.dirty = False

    try:
        with SessionLocal() as db, tenant_scope(room.tenant_id):
            from sqlalchemy import select

            row = db.scalar(
                select(YjsDocument).where(
                    YjsDocument.document_id == room.document_id
                )
            )
            if row is None:
                row = YjsDocument(
                    document_id=room.document_id,
                    document_kind="doc",
                    update_log=snapshot,
                    state_vector=None,
                    last_modified_by_id=user_id,
                    active_user_count=room.user_count,
                )
                db.add(row)
            else:
                row.update_log = snapshot
                if user_id:
                    row.last_modified_by_id = user_id
                row.active_user_count = room.user_count
            db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("yjs persist failed for %s/%s", room.tenant_id, room.document_id)


def _update_active_count(
    tenant_id: str, document_id: str, *, delta: int, user_id: str | None
) -> None:
    """Best-effort bump of ``active_user_count`` on join/leave.

    Failures are swallowed — the count is observability, not correctness.
    """
    try:
        with SessionLocal() as db, tenant_scope(tenant_id):
            from sqlalchemy import select

            row = db.scalar(
                select(YjsDocument).where(
                    YjsDocument.document_id == document_id
                )
            )
            if row is None:
                if delta <= 0:
                    return
                row = YjsDocument(
                    document_id=document_id,
                    document_kind="doc",
                    active_user_count=max(0, delta),
                    last_modified_by_id=user_id,
                )
                db.add(row)
            else:
                row.active_user_count = max(0, (row.active_user_count or 0) + delta)
            db.commit()
    except Exception:  # noqa: BLE001
        logger.debug("active count update failed", exc_info=True)


def reset_for_tests() -> None:
    """Test-only helper. Wipes the in-memory room registry."""
    with _rooms_lock:
        _rooms.clear()
