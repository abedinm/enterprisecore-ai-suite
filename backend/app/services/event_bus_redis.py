"""Optional Redis Streams backend for the event bus.

Only loaded when ``REDIS_URL`` env is set. Pushes each ``Event`` onto a
per-tenant stream (``events:<tenant_id>``) so a separate worker process can
dispatch webhooks without sharing memory with the API server. The base
``publish()`` already dispatches in-process, so this exists for the
"need horizontal scale" case rather than as the only delivery path.

We deliberately avoid importing ``redis`` at module import time: tests that
don't have Redis available shouldn't pay the import cost.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from app.services.event_bus import Event


_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    try:
        import redis  # type: ignore

        _client = redis.Redis.from_url(url, decode_responses=True)
        return _client
    except Exception:  # pragma: no cover
        logger.exception("failed to connect to Redis at %s", url)
        return None


def push_to_stream(event: "Event") -> None:
    """Append ``event`` to ``events:<tenant_id>``. Best-effort; failure logged."""

    client = _get_client()
    if client is None:
        return
    stream = f"events:{event.tenant_id or 'global'}"
    body = {
        "id": event.id,
        "type": event.type,
        "tenant_id": event.tenant_id or "",
        "user_id": event.user_id or "",
        "occurred_at": event.occurred_at.isoformat()
        if isinstance(event.occurred_at, datetime)
        else str(event.occurred_at),
        "payload": json.dumps(event.payload),
    }
    try:
        client.xadd(stream, body, maxlen=10000, approximate=True)
    except Exception:  # pragma: no cover
        logger.exception("xadd to %s failed", stream)


CONSUMER_GROUP = "enterprisecore"
