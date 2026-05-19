"""Audit-log helpers."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import AuditLog, User


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
        detail=json.dumps(detail or {}, default=str),
    )
    db.add(log)
    return log
