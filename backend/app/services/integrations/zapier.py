"""Zapier integration — outbound webhook + inbound API-key trigger.

Zapier is the easiest of the three because it offers no OAuth flow of its
own; the customer pastes a "Catch Hook" URL into the integration config
and we POST to it on every matching event. In the other direction,
Zapier-built "Zaps" call our ``POST /integrations/zapier/inbound`` with a
static API key the customer copied when they installed the integration.

Why bother when we already have generic outbound webhooks?

  * Tenant-friendly: users think of "I want a Zapier integration", not
    "let me build a webhook subscription".
  * Inbound surface: the generic webhook flow is one-way; Zapier needs a
    two-way bridge to be useful (5,000+ apps in one).
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import decrypt_field, encrypt_field
from app.core.exceptions import NotFoundError, ValidationFailed
from app.core.tenant_context import bypass_tenant_filter
from app.models.integrations import TenantIntegration
from app.services.integrations.base import Integration
from app.services.integrations.slack import _delete_integration, _event_matches

if TYPE_CHECKING:  # pragma: no cover
    from app.services.event_bus import Event

logger = logging.getLogger(__name__)


_http_client_factory = None


def set_http_client_factory(factory):
    """Tests use this to substitute a fake httpx client."""
    global _http_client_factory
    _http_client_factory = factory


def _http_client():
    if _http_client_factory is not None:
        return _http_client_factory()
    return httpx.Client(timeout=10.0)


class ZapierIntegration(Integration):
    """Zapier connector — outbound webhook + inbound API surface."""

    key = "zapier"
    name = "Zapier"
    category = "automation"
    description = (
        "Bridge any of Zapier's 5,000+ apps into EnterpriseCore. "
        "Outbound: events POST to your Zapier catch-hook. "
        "Inbound: Zaps call our API with a static key."
    )
    default_event_types = ["*"]

    @classmethod
    def is_configurable(cls) -> bool:
        # Zapier doesn't need any deployment-level config — every tenant
        # installs it locally with their own catch-hook URL.
        return True

    # ---- install / uninstall -------------------------------------------
    def install_url(self, tenant_id: str, redirect_url: str) -> str:
        # Zapier has no OAuth; installation is handled by ``install_static``.
        return ""

    def install_static(
        self,
        tenant_id: str,
        db: Session,
        *,
        installed_by_user_id: str | None = None,
    ) -> tuple[TenantIntegration, str]:
        """Idempotent install: returns the row + the *plaintext* API key.

        The API key is shown exactly once at install time; subsequent
        GETs never reveal it (it's stored encrypted under the tenant DEK
        in ``access_token_encrypted``).
        """
        api_key = "zk_" + secrets.token_urlsafe(32)
        with bypass_tenant_filter():
            row = db.scalar(
                select(TenantIntegration).where(
                    TenantIntegration.tenant_id == tenant_id,
                    TenantIntegration.key == self.key,
                )
            )
        now = datetime.now(timezone.utc)
        if row is None:
            row = TenantIntegration(
                tenant_id=tenant_id,
                key=self.key,
                name=self.name,
                installed_by_user_id=installed_by_user_id,
                installed_at=now,
                config={
                    "outbound_webhook_url": "",
                    "event_filter": list(self.default_event_types),
                },
                access_token_encrypted=encrypt_field(api_key, tenant_id, db=db),
            )
            db.add(row)
        else:
            # Re-install rotates the key.
            row.access_token_encrypted = encrypt_field(api_key, tenant_id, db=db)
            row.is_enabled = True
        db.commit()
        db.refresh(row)
        return row, api_key

    def handle_oauth_callback(
        self,
        tenant_id: str,
        code: str,
        state: str,
        db: Session,
    ) -> TenantIntegration:
        raise NotImplementedError("Zapier does not use OAuth — use install_static().")

    def uninstall(self, tenant_id: str, db: Session) -> None:
        _delete_integration(db, tenant_id, self.key)

    # ---- outbound event posting ----------------------------------------
    def handle_event(self, event: "Event", integration: TenantIntegration) -> None:
        if not integration.is_enabled:
            return
        cfg = integration.config or {}
        url = (cfg.get("outbound_webhook_url") or "").strip()
        if not url:
            return
        event_filter = cfg.get("event_filter") or self.default_event_types
        if not _event_matches(event.type, event_filter):
            return

        body = {
            "id": event.id,
            "type": event.type,
            "tenant_id": event.tenant_id,
            "occurred_at": event.occurred_at.isoformat(),
            "payload": event.payload,
        }
        client = _http_client()
        try:
            client.post(
                url,
                content=json.dumps(body, default=str).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=10.0,
            )
        except Exception:
            logger.exception("Zapier outbound POST failed for %s", event.type)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    # ---- inbound API-key call ------------------------------------------
    def find_by_api_key(self, db: Session, api_key: str) -> TenantIntegration | None:
        """Look up the TenantIntegration row that owns ``api_key``.

        We scan every Zapier row (rare table; trivial cost) and try to
        decrypt each — only the right tenant's DEK will produce the
        matching plaintext. This keeps API keys opaque at rest while
        avoiding a global lookup table.
        """
        with bypass_tenant_filter():
            rows = db.scalars(
                select(TenantIntegration).where(TenantIntegration.key == self.key)
            ).all()
        for row in rows:
            if not row.access_token_encrypted:
                continue
            try:
                if decrypt_field(row.access_token_encrypted, row.tenant_id, db=db) == api_key:
                    return row
            except Exception:
                continue
        return None

    def handle_inbound(
        self,
        payload: dict,
        headers: dict,
        integration: TenantIntegration,
    ) -> dict | None:
        """Dispatch a Zapier inbound call to the right internal action.

        ``payload`` shape: ``{"action": "create_crm_lead", "data": {...}}``.
        """
        action = (payload.get("action") or "").lower()
        data = payload.get("data") or {}
        from app.services.event_bus import publish_event

        if action == "create_crm_lead":
            return _action_create_crm_lead(data, integration)
        if action == "create_calendar_event":
            ev = publish_event(
                "projects.project.created",
                payload={
                    "title": data.get("title", "Calendar event from Zapier"),
                    "kickoff_at": data.get("when"),
                    "description": data.get("description", ""),
                    "source": "zapier",
                },
                tenant_id=integration.tenant_id,
            )
            return {"ok": True, "event_id": ev.id, "action": action}
        if action == "add_note":
            return _action_add_note(data, integration)
        raise ValidationFailed(f"Unknown Zapier inbound action: {action}")


def _action_create_crm_lead(data: dict, integration: TenantIntegration) -> dict:
    """Create a CRM Lead (+ underlying Contact) from a Zapier inbound payload.

    The Lead model points at a Contact via FK rather than carrying name/email
    columns of its own, so we create both inside one transaction."""
    from app.db.session import SessionLocal
    from app.models.crm import Contact, Lead
    from app.core.tenant_context import tenant_scope
    from app.services.event_bus import publish_event

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    if not name and not email:
        raise ValidationFailed("create_crm_lead requires at least name or email")

    with SessionLocal() as db, tenant_scope(integration.tenant_id):
        contact = Contact(
            name=name or email or "Unknown",
            email=email or None,
            company=data.get("company") or None,
        )
        db.add(contact)
        db.flush()
        lead = Lead(
            contact_id=contact.id,
            source=data.get("source") or "zapier",
            status="new",
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        publish_event(
            "crm.lead.created",
            payload={
                "lead_id": lead.id,
                "name": contact.name,
                "source": lead.source,
            },
            tenant_id=integration.tenant_id,
        )
        return {"ok": True, "lead_id": lead.id, "action": "create_crm_lead"}


def _action_add_note(data: dict, integration: TenantIntegration) -> dict:
    """Create a Notification row for a tenant admin.

    We avoid pulling in a new note-model concept and use the existing
    Notification table — it's the closest fit for "drop a line in the
    tenant's inbox from a Zap".
    """
    from app.db.session import SessionLocal
    from app.models.user import Notification
    from app.core.tenant_context import tenant_scope

    body = (data.get("body") or "").strip()
    if not body:
        raise ValidationFailed("add_note requires a body")
    with SessionLocal() as db, tenant_scope(integration.tenant_id):
        note = Notification(
            user_id=None,
            title=data.get("title") or "Note from Zapier",
            body=body,
            level="info",
        )
        db.add(note)
        db.commit()
        db.refresh(note)
        return {"ok": True, "notification_id": note.id, "action": "add_note"}
