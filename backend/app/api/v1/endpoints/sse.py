"""Server-Sent Events — unidirectional channel for job status updates.

SSE is the boring-and-bulletproof companion to WebSockets:

* Plain HTTP GET, so any corporate proxy that allows the rest of the
  API will allow this. Sites that block WebSockets typically don't
  block ``text/event-stream``.
* One-way only, which is exactly what we need for job-status updates
  — the client never has to send anything once the stream is open.

The implementation here uses ``asyncio.Queue`` per connection. The
event-bus bridge in :mod:`app.services.realtime` doesn't know about
SSE directly — instead, each connection registers a queue that the
job-status broker writes to. When the client disconnects, the
``StreamingResponse`` generator raises ``CancelledError`` which we
catch to unregister.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Per-user queue registry
# ---------------------------------------------------------------------------
# Multiple SSE clients per user are allowed (e.g. two browser tabs). Each
# tab gets its own queue and receives a copy of every job event for that
# user.
_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
_subs_lock = asyncio.Lock()
_bus_wired = False


async def _register(user_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    async with _subs_lock:
        _subscribers[user_id].add(q)
    _ensure_bus_wired()
    return q


async def _unregister(user_id: str, q: asyncio.Queue) -> None:
    async with _subs_lock:
        bucket = _subscribers.get(user_id)
        if bucket is None:
            return
        bucket.discard(q)
        if not bucket:
            _subscribers.pop(user_id, None)


def _ensure_bus_wired() -> None:
    """Wire the event bus into SSE fan-out once per process."""
    global _bus_wired
    if _bus_wired:
        return
    try:
        from app.services.event_bus import subscribe
    except Exception:
        return

    def _on_job_event(ev) -> None:
        # Resolve the target user — events fired from `app.services.jobs`
        # carry the creator id in either ev.user_id or payload["user_id"].
        uid = ev.user_id or (ev.payload or {}).get("user_id")
        if not uid:
            return
        bucket = _subscribers.get(uid)
        if not bucket:
            return
        msg = {
            "type": ev.type,
            "tenant_id": ev.tenant_id,
            "occurred_at": ev.occurred_at.isoformat(),
            "data": ev.payload or {},
        }
        for q in list(bucket):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                # Slow consumer — drop the message rather than block the
                # publisher. The frontend can recover via the normal
                # polling REST endpoint.
                logger.debug("SSE queue full for user %s", uid)

    for evt in ("jobs.queued", "jobs.started", "jobs.completed", "jobs.failed"):
        subscribe(evt, _on_job_event)
    _bus_wired = True


def emit_job_event(user_id: str, event_type: str, data: dict) -> None:
    """Synchronous helper for the jobs service to push an update.

    Use this from places that don't go through the event bus (the worker
    process, for example). When called from the ASGI loop the queue put
    is best-effort.
    """
    bucket = _subscribers.get(user_id)
    if not bucket:
        return
    msg = {
        "type": event_type,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "data": data or {},
    }
    for q in list(bucket):
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            pass


# ---------------------------------------------------------------------------
# Stream generator
# ---------------------------------------------------------------------------
async def _event_stream(
    request: Request, user_id: str
) -> AsyncIterator[bytes]:
    """Yield SSE-formatted bytes for the given user.

    The format is documented in the WHATWG SSE spec — one event is::

        event: <type>
        data: <json>
        id: <optional>
        \n

    We also emit periodic comment lines (``: heartbeat``) so transparent
    proxies that close idle connections will keep this one open.
    """
    q = await _register(user_id)
    # Initial "hello" so the client knows the stream is alive.
    yield _format_sse("hello", {"user_id": user_id, "ts": _utc_iso()})

    HEARTBEAT_S = 25.0
    try:
        while True:
            if await request.is_disconnected():
                return
            try:
                msg = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_S)
            except asyncio.TimeoutError:
                # Heartbeat — keep the proxy from closing us.
                yield b": heartbeat\n\n"
                continue
            yield _format_sse(msg.get("type", "message"), msg)
    except asyncio.CancelledError:
        return
    finally:
        await _unregister(user_id, q)


def _format_sse(event_type: str, data: dict) -> bytes:
    payload = json.dumps(data, default=str)
    # ``event`` is optional but very useful for client-side dispatch.
    return f"event: {event_type}\ndata: {payload}\n\n".encode("utf-8")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@router.get("/jobs")
async def sse_jobs(
    request: Request,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream job-lifecycle events for the authenticated user.

    Browsers will keep the connection open and auto-reconnect on drop;
    the JS ``EventSource`` API handles that natively. No special
    cancellation semantics on our side — when the response generator
    finishes (client closed / server shutting down), the queue is
    unregistered in the ``finally`` block.
    """
    return StreamingResponse(
        _event_stream(request, user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # nginx: don't buffer.
            "Connection": "keep-alive",
        },
    )
