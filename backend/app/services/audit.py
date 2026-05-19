"""Audit-log helpers."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import AuditLog, User


def _coerce_detail(detail: dict[str, Any] | None) -> dict:
    """Ensure the dict is JSON-serialisable (Decimal, datetime, etc.).

    SQLAlchemy's JSON column type wants a real dict; non-primitive values
    inside are serialised by the dialect's JSON encoder, but Decimal and
    datetime aren't supported on every dialect. Round-trip through
    json.dumps(..., default=str) to coerce them to strings safely.
    """
    if not detail:
        return {}
    return json.loads(json.dumps(detail, default=str))


def record_audit(
    db: Session,
    *,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    ip_address: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    log = AuditLog(
        actor_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=ip_address,
        detail=_coerce_detail(detail),
    )
    db.add(log)
    return log
