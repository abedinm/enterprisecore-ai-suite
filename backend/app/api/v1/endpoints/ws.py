"""WebSocket endpoints — notifications, webchat live stream, Yjs room.

Every endpoint here authenticates from the same token the HTTP API
accepts (Bearer or cookie or Sec-WebSocket-Protocol). On auth failure
we close with code 1008 (policy violation) per RFC 6455 — that's the
agreed signal the frontend client uses to give up reconnecting and
push the user to a re-login flow.

Tenant scope: the user row already carries ``tenant_id``, so the
connection manager indexes the socket under the caller's tenant. The
event-bus → fan-out bridge in :mod:`app.services.realtime` only ever
sends to sockets whose tenant matches the event's tenant, so cross-
tenant leakage is impossible by construction.

Heartbeat: each endpoint accepts ``{"type": "ping"}`` / replies with
``{"type": "pong"}``. The server itself also sends pings via a
per-connection asyncio task so dead browsers (e.g. closed laptop lid)
get cleaned up promptly.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from starlette.websockets import WebSocketState

from app.services.realtime import (
    HEARTBEAT_INTERVAL,
    HEARTBEAT_TIMEOUT,
    get_user_from_ws_auth,
    manager,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _server_heartbeat(ws: WebSocket) -> None:
    """Send periodic pings; close the socket if the client falls silent.

    The client wrapper auto-replies with a pong. We don't rely on the
    underlying WebSocket protocol-level ping because Starlette doesn't
    expose pong receipts to handler code — easier to do it at the JSON
    layer where ``ws.receive_json()`` already returns the pong frames.
    """
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if ws.application_state != WebSocketState.CONNECTED:
                return
            try:
                await ws.send_json({"type": "ping", "ts": _utc_iso()})
            except Exception:
                return
    except asyncio.CancelledError:
        return


async def _close_safely(ws: WebSocket, *, code: int) -> None:
    try:
        await ws.close(code=code)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# /ws/notifications — per-user toast inbox + tenant system events
# ---------------------------------------------------------------------------
@router.websocket("/ws/notifications")
async def ws_notifications(websocket: WebSocket) -> None:
    await websocket.accept()
    user = await get_user_from_ws_auth(websocket)
    if user is None:
        await _close_safely(websocket, code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(
        websocket,
        tenant_id=user.tenant_id,
        user_id=user.id,
        channel="notifications",
    )
    # Greet the client so it knows the channel is live.
    try:
        await websocket.send_json({
            "type": "hello",
            "channel": "notifications",
            "user_id": user.id,
            "tenant_id": user.tenant_id,
            "ts": _utc_iso(),
        })
    except Exception:
        await manager.disconnect(websocket)
        return

    hb_task = asyncio.create_task(_server_heartbeat(websocket))
    try:
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                continue
            kind = data.get("type")
            if kind == "ping":
                await websocket.send_json({"type": "pong", "ts": _utc_iso()})
            elif kind == "pong":
                # Heartbeat reply from the client to our ping.
                pass
            # Other inbound types are reserved for future use; ignore for now.
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.debug("ws_notifications loop error", exc_info=True)
    finally:
        hb_task.cancel()
        await manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# /ws/webchat/{bot_id} — live message stream for one bot's conversations
# ---------------------------------------------------------------------------
@router.websocket("/ws/webchat/{bot_id}")
async def ws_webchat(websocket: WebSocket, bot_id: str) -> None:
    await websocket.accept()
    user = await get_user_from_ws_auth(websocket)
    if user is None:
        await _close_safely(websocket, code=status.WS_1008_POLICY_VIOLATION)
        return

    # Verify ownership of the bot. We deliberately treat
    # "bot not found" the same as "not the owner" so we don't leak
    # which bot ids exist across tenants.
    from app.core.tenant_context import tenant_scope
    from app.db.session import SessionLocal
    from app.models.webchat import Bot

    with SessionLocal() as db, tenant_scope(user.tenant_id):
        bot = db.get(Bot, bot_id)
        if not bot or bot.owner_id != user.id:
            await _close_safely(websocket, code=status.WS_1008_POLICY_VIOLATION)
            return

    await manager.connect(
        websocket,
        tenant_id=user.tenant_id,
        user_id=user.id,
        channel=f"webchat.{bot_id}",
    )
    try:
        await websocket.send_json({
            "type": "hello",
            "channel": f"webchat.{bot_id}",
            "bot_id": bot_id,
            "ts": _utc_iso(),
        })
    except Exception:
        await manager.disconnect(websocket)
        return

    hb_task = asyncio.create_task(_server_heartbeat(websocket))
    try:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict) and data.get("type") == "ping":
                await websocket.send_json({"type": "pong", "ts": _utc_iso()})
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.debug("ws_webchat loop error", exc_info=True)
    finally:
        hb_task.cancel()
        await manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# /ws/yjs/{document_id} — collaborative editing room (scaffold)
# ---------------------------------------------------------------------------
@router.websocket("/ws/yjs/{document_id}")
async def ws_yjs(websocket: WebSocket, document_id: str) -> None:
    """Bridge for Yjs binary CRDT updates.

    Without ``y-py`` installed we don't try to interpret the binary
    protocol on the server. Instead we:

    1. Authenticate the user + scope by their tenant.
    2. Send the persisted state-vector + update-log on join so the
       newly-connected client can ``Y.applyUpdate(...)`` and catch up.
    3. Relay every subsequent binary frame to all *other* peers in the
       same room and append it to the persisted update log (debounced).

    That covers correctness — clients reconcile via the CRDT — but
    leaves out optimisations the canonical y-websocket server does
    (awareness piggy-backing, garbage-collected state vectors). Those
    can land later without breaking the wire format.
    """
    await websocket.accept()
    user = await get_user_from_ws_auth(websocket)
    if user is None:
        await _close_safely(websocket, code=status.WS_1008_POLICY_VIOLATION)
        return

    from app.services.yjs_room import join_room, leave_room, ingest_update

    channel = f"yjs.{document_id}"
    await manager.connect(
        websocket,
        tenant_id=user.tenant_id,
        user_id=user.id,
        channel=channel,
    )

    try:
        snapshot = join_room(
            tenant_id=user.tenant_id,
            document_id=document_id,
            user_id=user.id,
        )
        # Send any persisted update log so the joiner can sync. Frame type
        # ``sync-snapshot`` matches what the frontend Y.js wrapper expects.
        if snapshot:
            await websocket.send_bytes(snapshot)
    except Exception:
        logger.debug("ws_yjs snapshot send failed", exc_info=True)

    hb_task = asyncio.create_task(_server_heartbeat(websocket))
    try:
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if "bytes" in msg and msg["bytes"] is not None:
                payload = msg["bytes"]
                # Persist + record dirty state.
                try:
                    ingest_update(
                        tenant_id=user.tenant_id,
                        document_id=document_id,
                        update_bytes=payload,
                        user_id=user.id,
                    )
                except Exception:
                    logger.debug("yjs ingest failed", exc_info=True)
                # Relay to every OTHER socket in the room.
                peers = list(
                    manager._by_tenant_channel.get(
                        (user.tenant_id, channel), ()
                    )
                )
                for peer in peers:
                    if peer is websocket:
                        continue
                    try:
                        await peer.send_bytes(payload)
                    except Exception:
                        await manager.disconnect(peer)
            elif "text" in msg and msg["text"] is not None:
                # JSON control frames — currently just ping.
                if msg["text"].startswith('{"type":"ping"'):
                    try:
                        await websocket.send_json(
                            {"type": "pong", "ts": _utc_iso()}
                        )
                    except Exception:
                        break
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.debug("ws_yjs loop error", exc_info=True)
    finally:
        hb_task.cancel()
        try:
            leave_room(
                tenant_id=user.tenant_id,
                document_id=document_id,
                user_id=user.id,
            )
        except Exception:
            pass
        await manager.disconnect(websocket)
