"""Abstract base for all third-party integrations.

A connector subclasses :class:`Integration`, sets the four class
attributes (``key`` / ``name`` / ``category`` / ``description``), and
implements the install / uninstall / OAuth-callback / event-handler hooks.
The registry instantiates one stateless singleton per connector at import
time; per-tenant state lives entirely in :class:`TenantIntegration` rows.

Why "stateless"? Connector instances are shared across tenants by design
— they hold no tenant-specific data themselves. Every method that touches
tenant data takes ``tenant_id`` (or the ``TenantIntegration`` row) as a
parameter so two tenants can install the same connector concurrently
without contention.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:  # pragma: no cover
    from app.models.integrations import TenantIntegration
    from app.services.event_bus import Event

logger = logging.getLogger(__name__)


class Integration(ABC):
    """Abstract base every connector inherits from.

    Subclasses MUST set ``key`` (stable identifier used in the URL),
    ``name`` (display label), ``category`` (free-form bucket the UI groups
    by — ``messaging`` / ``calendar`` / ``automation``), and
    ``description``.
    """

    key: str = ""
    name: str = ""
    category: str = ""
    description: str = ""

    # Event types this connector defaults to listening for. Subscriber
    # registration honours the per-tenant ``event_filter`` config, falling
    # back to this when the customer hasn't customised it. ``["*"]`` would
    # mean "everything"; we recommend keeping the default narrow.
    default_event_types: list[str] = []

    # When False the catalog shows the connector as "Available — admin must
    # configure credentials in environment". Used by Slack + Google where
    # the OAuth app credentials are owned by the deployment, not per-tenant.
    @classmethod
    def is_configurable(cls) -> bool:
        """Return True when the deployment has the env vars / libraries
        needed for this integration to actually work. Default: always
        configurable; subclasses override to gate on real env vars."""
        return True

    @abstractmethod
    def install_url(self, tenant_id: str, redirect_url: str) -> str:
        """Return the OAuth authorization URL the user is sent to.

        ``redirect_url`` is the public callback the third-party will
        redirect back to (typically ``/api/v1/integrations/oauth/callback``).
        Connectors that don't use OAuth (Zapier) return an empty string
        and rely on :meth:`install_static` / endpoint-level handling.
        """

    @abstractmethod
    def handle_oauth_callback(
        self,
        tenant_id: str,
        code: str,
        state: str,
        db: Session,
    ) -> "TenantIntegration":
        """Exchange ``code`` for tokens, persist a TenantIntegration row.

        Returns the row so the endpoint can log + audit the install.
        Connectors not doing OAuth raise :class:`NotImplementedError`.
        """

    @abstractmethod
    def uninstall(self, tenant_id: str, db: Session) -> None:
        """Revoke tokens at the third-party side (best effort) and delete
        the TenantIntegration row. Idempotent."""

    @abstractmethod
    def handle_event(self, event: "Event", integration: "TenantIntegration") -> None:
        """Called by the event bus for events this integration cares about.

        The default registration loop subscribes the connector to its
        ``default_event_types``; the handler is expected to honour the
        tenant's ``event_filter`` config and silently skip events outside
        it. Exceptions are caught + logged by the event bus, so a
        misbehaving connector can't take down the publishing endpoint.
        """

    def handle_inbound(
        self,
        payload: dict,
        headers: dict,
        integration: "TenantIntegration",
    ) -> dict | None:
        """Optional inbound webhook receiver. Connectors that don't
        support inbound calls leave this returning None."""
        return None

    # ---- helpers --------------------------------------------------------
    def fire_test(self, integration: "TenantIntegration") -> dict:
        """Fire a synthetic event so the customer can confirm the wire is
        live. Default implementation publishes ``webhook.test`` scoped to
        the integration's tenant; connectors override when a smoke event
        of their own kind makes more sense.
        """
        from app.services.event_bus import publish_event

        ev = publish_event(
            "webhook.test",
            payload={"integration": self.key, "test": True},
            tenant_id=integration.tenant_id,
        )
        return {"event_id": ev.id, "status": "queued"}
