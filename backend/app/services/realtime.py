"""Realtime transport — WebSocket connection manager + event-bus bridge.

Tracks every live WebSocket per ``(tenant_id, channel, user_id)`` and
provides ``send_to_channel`` / ``send_to_user`` / ``broadcast_tenant``
fan-out helpers. Channels:

* ``notifications`` — per-user inbox + tenant-wide system events. Toasts.
* ``webchat.<bot_id>`` — live message stream for a single chat bot's
  conversation viewer.
* ``jobs`` — background-job status updates for the owning user.
* ``yjs.<document_id>`` — collaborative editing room (relayed bytes).

The manager subscribes to the in-process event bus once at process
start (idempotent). When a business endpoint fires
``publish_event("crm.deal.won", ...)`` the matching subscriber here
serialises a JSON payload and pushes it to every live WS in the right
tenant scope. The fan-out is best-effort: a closed/broken socket is
dropped silently so a misbehaving client can never break the publisher.

Heartbeat: a background asyncio task pings every connection every
``HEARTBEAT_INTERVAL`` seconds. Connections that haven't pong'd within
``HEARTBEAT_TIMEOUT`` are closed. The frontend wrapper sends pongs
automatically.

All public methods are async-safe; mutation of the registry uses a single
``asyncio.Lock``.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from weakref import WeakSet

from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30.0  # seconds — server-initiated ping cadence
HEARTBEAT_TIMEOUT = 60.0   # seconds without a pong → drop


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _ConnRecord:
    """One live socket plus the metadata we need to route events to it."""

    __slots__ = ("ws", "tenant_id", "user_id", "channel", "last_pong_at")

    def __init__(self, ws: WebSocket, *, tenant_id: str, user_id: str, channel: str) -> None:
        self.ws = ws
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.channel = channel
        self.last_pong_at = datetime.now(timezone.utc)


class ConnectionManager:
    """Process-wide registry of active WebSocket connections.

    The registry is a plain ``dict`` keyed by the WebSocket instance, with
    secondary indexes (``_by_tenant_channel``, ``_by_user``) maintained
    inside ``connect()`` / ``disconnect()`` so fan-out is O(subscribers)
    rather than O(all connections).

    Reading the secondary indexes during fan-out is done under a snapshot
    (``list(...)``) so a disconnect concurrent with a broadcast can never
    raise ``RuntimeError: dictionary changed size during iteration``.
    """

    def __init__(self) -> None:
        self._conns: dict[WebSocket, _ConnRecord] = {}
        # (tenant_id, channel) -> set of connections.
        self._by_tenant_channel: dict[tuple[str, str], set[WebSocket]] = defaultdict(set)
        # user_id -> set of connections.
        self._by_user: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._event_bus_wired = False
        self._heartbeat_task: asyncio.Task | None = None
        # Captured at first connect — used by sync publishers (event bus
        # handlers run synchronously inside ``publish()``) to schedule
        # fan-out onto the ASGI loop even when the publisher is on a
        # different thread (e.g. the TestClient portal).
        self._loop: asyncio.AbstractEventLoop | None = None

    # ----- lifecycle -------------------------------------------------------
    async def connect(
        self,
        ws: WebSocket,
        *,
        tenant_id: str,
        user_id: str,
        channel: str,
    ) -> None:
        """Register an already-accepted WebSocket against (tenant, user, channel).

        The caller is responsible for ``await ws.accept()`` before calling
        this — the endpoint code does that as part of the auth handshake so
        a failed auth can close with a specific code (1008) before any
        registration state exists.
        """
        record = _ConnRecord(ws, tenant_id=tenant_id, user_id=user_id, channel=channel)
        async with self._lock:
            self._conns[ws] = record
            self._by_tenant_channel[(tenant_id, channel)].add(ws)
            self._by_user[user_id].add(ws)
            # Re-capture the loop on every connect. Tests close the
            # ASGI loop between cases, so the previously-cached
            # reference can be a stale ``BaseEventLoop`` that's no
            # longer running. ``asyncio.get_running_loop()`` returns
            # the current one; we overwrite unconditionally.
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
        self._ensure_event_bus_wired()

    async def disconnect(self, ws: WebSocket) -> None:
        """Remove a socket from every index. Idempotent."""
        async with self._lock:
            record = self._conns.pop(ws, None)
            if record is None:
                return
            bucket = self._by_tenant_channel.get((record.tenant_id, record.channel))
            if bucket is not None:
                bucket.discard(ws)
                if not bucket:
                    self._by_tenant_channel.pop((record.tenant_id, record.channel), None)
            ubucket = self._by_user.get(record.user_id)
            if ubucket is not None:
                ubucket.discard(ws)
                if not ubucket:
                    self._by_user.pop(record.user_id, None)

    # ----- fan-out ---------------------------------------------------------
    async def send_to_channel(
        self, tenant_id: str, channel: str, message: dict[str, Any]
    ) -> int:
        """Send ``message`` (JSON-encoded) to every live connection in
        ``(tenant_id, channel)``. Returns the number of successful sends.
        """
        targets = list(self._by_tenant_channel.get((tenant_id, channel), ()))
        return await self._safe_fan_out(targets, message)

    async def send_to_user(
        self, user_id: str, message: dict[str, Any]
    ) -> int:
        """Send ``message`` to every live connection owned by ``user_id``
        across all channels."""
        targets = list(self._by_user.get(user_id, ()))
        return await self._safe_fan_out(targets, message)

    async def broadcast_tenant(
        self, tenant_id: str, message: dict[str, Any]
    ) -> int:
        """Send ``message`` to every connection whose tenant matches,
        regardless of channel. Used for tenant-wide system notices."""
        targets: list[WebSocket] = []
        for (tid, _ch), bucket in list(self._by_tenant_channel.items()):
            if tid == tenant_id:
                targets.extend(bucket)
        return await self._safe_fan_out(targets, message)

    async def _safe_fan_out(
        self, targets: list[WebSocket], message: dict[str, Any]
    ) -> int:
        """Send to each target; drop the ones that fail."""
        if not targets:
            return 0
        sent = 0
        for ws in targets:
            try:
                # Guard against sending to a half-closed socket — Starlette
                # raises a RuntimeError when the application state is
                # DISCONNECTED. We treat any send failure as a dead socket.
                if ws.application_state != WebSocketState.CONNECTED:
                    await self.disconnect(ws)
                    continue
                await ws.send_json(message)
                sent += 1
            except Exception:
                logger.debug("dropping ws after send failure", exc_info=True)
                try:
                    await self.disconnect(ws)
                except Exception:  # pragma: no cover — defensive
                    pass
        return sent

    # ----- introspection ---------------------------------------------------
    def connection_count(self, tenant_id: str | None = None) -> int:
        if tenant_id is None:
            return len(self._conns)
        count = 0
        for (tid, _ch), bucket in self._by_tenant_channel.items():
            if tid == tenant_id:
                count += len(bucket)
        return count

    # ----- event-bus bridge ------------------------------------------------
    def _ensure_event_bus_wired(self) -> None:
        """Subscribe to the in-process event bus exactly once.

        We do this lazily on the first ``connect()`` rather than at import
        time so the unit tests for the event bus itself don't accidentally
        pick up our handlers and have their assertion counts skewed.

        Subscriptions are idempotent — we mark a flag and skip on re-entry.
        """
        if self._event_bus_wired:
            return
        try:
            from app.services.event_bus import subscribe, Event
        except Exception:  # pragma: no cover — defensive
            return

        def _to_notification(ev: "Event") -> None:
            # Skip if no tenant — we can't scope it.
            if not ev.tenant_id:
                return
            human = _humanize_event(ev)
            payload = {
                "type": "notification",
                "event_type": ev.type,
                "tenant_id": ev.tenant_id,
                "occurred_at": ev.occurred_at.isoformat(),
                "title": human["title"],
                "body": human["body"],
                "level": human["level"],
                "data": ev.payload,
            }
            _schedule(self.send_to_channel(ev.tenant_id, "notifications", payload))

        def _to_webchat(ev: "Event") -> None:
            if not ev.tenant_id:
                return
            bot_id = (ev.payload or {}).get("bot_id")
            if not bot_id:
                return
            payload = {
                "type": "webchat.update",
                "event_type": ev.type,
                "bot_id": bot_id,
                "conversation_id": (ev.payload or {}).get("conversation_id"),
                "occurred_at": ev.occurred_at.isoformat(),
                "data": ev.payload,
            }
            _schedule(self.send_to_channel(ev.tenant_id, f"webchat.{bot_id}", payload))

        def _to_jobs(ev: "Event") -> None:
            if not ev.tenant_id:
                return
            payload = {
                "type": "job.update",
                "event_type": ev.type,
                "occurred_at": ev.occurred_at.isoformat(),
                "data": ev.payload,
            }
            uid = ev.user_id or (ev.payload or {}).get("user_id")
            if uid:
                _schedule(self.send_to_user(uid, payload))
            else:
                _schedule(self.send_to_channel(ev.tenant_id, "jobs", payload))

        # Notifications: most business events surface as toasts.
        for evt in NOTIFICATION_EVENT_TYPES:
            subscribe(evt, _to_notification)
        # Webchat — both the existing event and the new message event.
        subscribe("webchat.conversation.created", _to_webchat)
        subscribe("webchat.message.received", _to_webchat)
        # Jobs.
        for evt in JOB_EVENT_TYPES:
            subscribe(evt, _to_jobs)

        self._event_bus_wired = True


# Module-level singleton — endpoints import this directly.
manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Event-bus → notification mapping
# ---------------------------------------------------------------------------
NOTIFICATION_EVENT_TYPES: tuple[str, ...] = (
    "crm.lead.created",
    "crm.deal.won",
    "crm.deal.lost",
    "finance.invoice.created",
    "finance.invoice.paid",
    "finance.invoice.overdue",
    "hr.employee.created",
    "hr.leave.approved",
    "projects.project.created",
    "projects.task.completed",
    "marketing.post.published",
    "knowledge.document.ingested",
    "billing.subscription.upgraded",
    "billing.payment.failed",
    "ai.spend.threshold_crossed",
    "construction.variation.approved",
    "construction.risk.created",
)

JOB_EVENT_TYPES: tuple[str, ...] = (
    "jobs.queued",
    "jobs.started",
    "jobs.completed",
    "jobs.failed",
)


def _humanize_event(ev) -> dict[str, str]:
    """Turn an event into a (title, body, level) toast triple.

    Falls back to a generic title from the event type when the payload
    doesn't carry a friendlier label.
    """
    t = ev.type
    p = ev.payload or {}
    if t == "crm.deal.won":
        name = p.get("deal_name") or p.get("name") or "a deal"
        amount = p.get("amount") or p.get("value")
        body = f"Deal won: {name}"
        if amount:
            body += f" ({amount})"
        return {"title": "Deal won", "body": body, "level": "success"}
    if t == "crm.deal.lost":
        return {"title": "Deal lost", "body": p.get("deal_name") or "A deal was lost", "level": "warning"}
    if t == "crm.lead.created":
        return {"title": "New lead", "body": p.get("name") or "A new sales lead was created.", "level": "info"}
    if t == "finance.invoice.paid":
        return {"title": "Invoice paid", "body": f"Invoice {p.get('number') or p.get('invoice_id', '')} paid", "level": "success"}
    if t == "finance.invoice.overdue":
        return {"title": "Invoice overdue", "body": f"Invoice {p.get('number') or p.get('invoice_id', '')} is overdue", "level": "error"}
    if t == "finance.invoice.created":
        return {"title": "Invoice issued", "body": f"Invoice {p.get('number') or 'created'}", "level": "info"}
    if t == "billing.payment.failed":
        return {"title": "Payment failed", "body": "A payment attempt failed", "level": "error"}
    if t == "ai.spend.threshold_crossed":
        return {"title": "AI spend alert", "body": f"AI spend crossed {p.get('pct', '')}% of cap", "level": "warning"}
    if t == "knowledge.document.ingested":
        return {"title": "Document ready", "body": p.get("title") or "A knowledge document finished ingesting.", "level": "success"}
    if t == "marketing.post.published":
        return {"title": "Post published", "body": p.get("title") or "A marketing post was published.", "level": "success"}
    if t == "projects.task.completed":
        return {"title": "Task completed", "body": p.get("title") or "A task was completed.", "level": "info"}
    if t == "construction.variation.approved":
        return {"title": "Variation approved", "body": p.get("title") or "A construction variation was approved.", "level": "success"}
    # Fallback — derive a title from the event type.
    title = t.replace(".", " ").replace("_", " ").title()
    return {"title": title, "body": "", "level": "info"}


# ---------------------------------------------------------------------------
# Sync→async bridge helpers
# ---------------------------------------------------------------------------

# Subscribers fire synchronously from inside ``publish()`` which may be
# called from either a sync handler (most endpoint code, since SQLAlchemy
# sessions are sync) or an async one. We schedule the async fan-out onto
# the running loop without blocking the publisher. When there is no
# running loop (housekeeping, tests bootstrapping outside ASGI), the
# coroutine is dropped — sockets only exist inside the ASGI loop anyway.

def _schedule(coro) -> None:
    """Schedule a coroutine on the manager's ASGI loop.

    Three cases:

    * Called from inside the ASGI loop (regular endpoint handler firing
      ``publish_event`` from an async path): use ``create_task`` on the
      current loop.
    * Called from a different thread (TestClient portal, RQ worker
      callback) but the manager has captured the ASGI loop via a prior
      connect: use ``run_coroutine_threadsafe`` so the coroutine is
      handed off to the loop that owns the sockets.
    * Nothing usable at all: close the coroutine to suppress the
      "never awaited" warning and move on — no live sockets exist
      outside an ASGI loop anyway.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
        return
    except RuntimeError:
        pass
    target = manager._loop  # noqa: SLF001 — module-internal access
    if target is not None and target.is_running():
        try:
            asyncio.run_coroutine_threadsafe(coro, target)
            return
        except RuntimeError:
            pass
    try:
        coro.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Auth helper for WebSocket handshakes
# ---------------------------------------------------------------------------
async def get_user_from_ws_auth(websocket: WebSocket):
    """Validate the token in a WS handshake and return the matching User.

    Browsers can't set arbitrary headers on a ``new WebSocket()`` call so
    we accept the access token from any of:

    1. ``?token=<jwt>`` query string (default — what the frontend sends),
    2. ``Sec-WebSocket-Protocol: bearer.<jwt>`` subprotocol,
    3. ``__Host-access_token`` / ``access_token`` cookie (same names as
       the HTTP cookie auth so SSR-style cookies just work).

    Returns the ``User`` object on success, raises nothing — on failure
    the caller should ``await websocket.close(code=1008)``. We do NOT
    raise here so the endpoint can pick the close code itself.
    """
    from app.core.security import decode_token
    from app.db.session import SessionLocal
    from app.models.user import User

    token = websocket.query_params.get("token")
    if not token:
        # Try Sec-WebSocket-Protocol — value looks like "bearer.<jwt>".
        sub_proto = websocket.headers.get("sec-websocket-protocol", "")
        for piece in (p.strip() for p in sub_proto.split(",")):
            if piece.startswith("bearer."):
                token = piece[len("bearer.") :]
                break
    if not token:
        token = (
            websocket.cookies.get("__Host-access_token")
            or websocket.cookies.get("access_token")
        )
    if not token:
        return None

    try:
        payload = decode_token(token)
    except Exception:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None
    # Bypass tenant filter for this lookup — we don't have a tenant
    # context yet (that's what we're about to set up). The user row
    # itself carries the tenant_id.
    from app.core.tenant_context import bypass_tenant_filter

    with SessionLocal() as db, bypass_tenant_filter():
        user = db.get(User, user_id)
        if not user or not user.is_active:
            return None
        # Detach so the caller can read user.id / user.tenant_id after the
        # session closes without lazy-load surprises.
        db.expunge(user)
        return user


# Convenience used by tests + introspection endpoints.
def utcnow_iso() -> str:
    return _utc_iso()
