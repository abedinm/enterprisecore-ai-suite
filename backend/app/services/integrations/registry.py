"""Connector registry — single source of truth for available integrations.

Importing this module instantiates one stateless singleton per connector.
Endpoint code looks them up via :func:`get_integration`; the lifespan
hook calls :func:`register_all_subscribers` so every installed connector
gets wired into the in-process event bus.

Adding a new connector is a two-line edit here + the connector module.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.db.session import SessionLocal
from app.models.integrations import TenantIntegration
from app.services.integrations.base import Integration
from app.services.integrations.docusign import DocuSignIntegration
from app.services.integrations.github import GitHubIntegration
from app.services.integrations.google_workspace import GoogleWorkspaceIntegration
from app.services.integrations.microsoft_365 import Microsoft365Integration
from app.services.integrations.microsoft_teams import MicrosoftTeamsIntegration
from app.services.integrations.slack import SlackIntegration
from app.services.integrations.zapier import ZapierIntegration

if TYPE_CHECKING:  # pragma: no cover
    from app.services.event_bus import Event

logger = logging.getLogger(__name__)


_REGISTRY: dict[str, Integration] = {
    SlackIntegration.key: SlackIntegration(),
    GoogleWorkspaceIntegration.key: GoogleWorkspaceIntegration(),
    ZapierIntegration.key: ZapierIntegration(),
    MicrosoftTeamsIntegration.key: MicrosoftTeamsIntegration(),
    Microsoft365Integration.key: Microsoft365Integration(),
    DocuSignIntegration.key: DocuSignIntegration(),
    GitHubIntegration.key: GitHubIntegration(),
}


def get_integration(key: str) -> Integration:
    """Return the singleton for ``key`` or raise KeyError."""
    if key not in _REGISTRY:
        raise KeyError(f"Unknown integration: {key}")
    return _REGISTRY[key]


def list_integrations() -> list[Integration]:
    """All known connectors in stable registration order."""
    return list(_REGISTRY.values())


def _dispatch_to_installed_connectors(event: "Event") -> None:
    """Forward an event to every installed TenantIntegration row whose
    connector's ``handle_event`` cares about it.

    Runs inside the publishing call site, so it must be cheap + bounded.
    Failures are caught and logged at the connector level (the connector's
    handler logs its own exception) and never propagate."""
    if event.tenant_id is None:
        return
    db = SessionLocal()
    try:
        with bypass_tenant_filter():
            rows = db.scalars(
                select(TenantIntegration).where(
                    TenantIntegration.tenant_id == event.tenant_id,
                    TenantIntegration.is_enabled.is_(True),
                )
            ).all()
        for row in rows:
            conn = _REGISTRY.get(row.key)
            if conn is None:
                continue
            try:
                conn.handle_event(event, row)
            except Exception:
                logger.exception(
                    "connector %s handle_event raised for event %s",
                    row.key,
                    event.type,
                )
    finally:
        db.close()


def register_all_subscribers() -> None:
    """Wire the registry into the event bus.

    Called from the FastAPI lifespan hook. Idempotent — subscribing the
    same callable twice doubles the delivery, so we unsubscribe first.
    """
    from app.services.event_bus import subscribe, unsubscribe

    # Unsubscribe defensively so re-running this in tests doesn't fan out
    # the same event twice.
    unsubscribe("*", _dispatch_to_installed_connectors)
    subscribe("*", _dispatch_to_installed_connectors)
