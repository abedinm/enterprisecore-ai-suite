"""DocuSign integration — e-signature envelopes for CRM proposals,
construction contracts, and Marketing-module contracts.

Flow:

  1. Customer hits ``POST /integrations/docusign/install`` and is redirected
     to ``account.docusign.com/oauth/auth``.
  2. DocuSign redirects back with a code; we exchange it for an
     access + refresh token via ``oauth/token``.
  3. Connector subscribes to ``crm.proposal.sent``,
     ``crm.contract.created``, ``construction.contract.created`` — each
     fires a call to DocuSign Envelopes API.
  4. DocuSign Connect posts status updates back to
     ``POST /api/v1/integrations/docusign/inbound`` which marks the local
     document signed + writes a CRM CommunicationEntry-style audit.

The "base URL" varies (``account-d.docusign.com`` for sandbox,
``account.docusign.com`` for production). Each tenant install records
the API base returned by ``userinfo`` so subsequent envelope calls hit
the right account host.
"""
from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.core.encryption import decrypt_field
from app.core.exceptions import ValidationFailed
from app.models.integrations import TenantIntegration
from app.services.integrations.base import Integration
from app.services.integrations.slack import (
    _delete_integration, _event_matches, _mark_used, _upsert_integration,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.services.event_bus import Event

logger = logging.getLogger(__name__)


_DEFAULT_SCOPES = "signature extended"


_http_client_factory = None


def set_http_client_factory(factory):
    """Tests use this to substitute a fake httpx client."""
    global _http_client_factory
    _http_client_factory = factory


def _http_client():
    if _http_client_factory is not None:
        return _http_client_factory()
    return httpx.Client(timeout=10.0)


def _oauth_base() -> str:
    """``DOCUSIGN_BASE_URL`` selects sandbox vs production. Defaults to
    sandbox so a developer running locally without env vars hits the
    safe account-d host."""
    return os.environ.get("DOCUSIGN_BASE_URL", "https://account-d.docusign.com").rstrip("/")


class DocuSignIntegration(Integration):
    """DocuSign e-signature connector."""

    key = "docusign"
    name = "DocuSign"
    category = "esignature"
    description = (
        "Send proposals + contracts for e-signature via DocuSign. "
        "Inbound webhook updates document status when signed."
    )
    default_event_types = [
        "crm.proposal.sent",
        "crm.contract.created",
        "construction.contract.created",
    ]

    @classmethod
    def is_configurable(cls) -> bool:
        return bool(os.environ.get("DOCUSIGN_CLIENT_ID")) and bool(
            os.environ.get("DOCUSIGN_CLIENT_SECRET")
        )

    # ---- install / OAuth ------------------------------------------------
    def install_url(self, tenant_id: str, redirect_url: str) -> str:
        client_id = os.environ.get("DOCUSIGN_CLIENT_ID", "")
        if not client_id:
            return "https://developers.docusign.com/platform/auth/"
        params = {
            "response_type": "code",
            "scope": _DEFAULT_SCOPES,
            "client_id": client_id,
            "redirect_uri": redirect_url,
            "state": f"docusign:{tenant_id}",
        }
        return f"{_oauth_base()}/oauth/auth?{urlencode(params)}"

    def handle_oauth_callback(
        self,
        tenant_id: str,
        code: str,
        state: str,
        db: Session,
    ) -> TenantIntegration:
        client_id = os.environ.get("DOCUSIGN_CLIENT_ID", "")
        client_secret = os.environ.get("DOCUSIGN_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            raise ValidationFailed("DocuSign OAuth credentials are not configured.")

        expected_state = f"docusign:{tenant_id}"
        if state != expected_state:
            raise ValidationFailed("DocuSign OAuth state mismatch.")

        client = _http_client()
        try:
            resp = client.post(
                f"{_oauth_base()}/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=10.0,
            )
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

        data = resp.json() if hasattr(resp, "json") else {}
        access_token = data.get("access_token")
        if not access_token:
            raise ValidationFailed(
                f"DocuSign OAuth failed: {data.get('error', 'no access_token')}"
            )
        config = {
            "account_id": data.get("account_id"),
            "api_base": data.get("base_uri") or os.environ.get(
                "DOCUSIGN_API_BASE", "https://demo.docusign.net"
            ),
            "default_sender_email": "",
            "auto_send": True,
            "event_filter": list(self.default_event_types),
        }
        return _upsert_integration(
            db,
            tenant_id=tenant_id,
            key=self.key,
            name=self.name,
            access_token=access_token,
            refresh_token=data.get("refresh_token") or "",
            config=config,
        )

    def uninstall(self, tenant_id: str, db: Session) -> None:
        _delete_integration(db, tenant_id, self.key)

    # ---- event handling -------------------------------------------------
    def handle_event(self, event: "Event", integration: TenantIntegration) -> None:
        if not integration.is_enabled:
            return
        cfg = integration.config or {}
        event_filter = cfg.get("event_filter") or self.default_event_types
        if not _event_matches(event.type, event_filter):
            return
        if not cfg.get("auto_send", True):
            return

        account_id = cfg.get("account_id")
        api_base = (cfg.get("api_base") or "").rstrip("/")
        if not account_id or not api_base:
            logger.info("DocuSign integration %s missing account/base", integration.id)
            return

        try:
            token = decrypt_field(
                integration.access_token_encrypted or "",
                integration.tenant_id,
                db=None,
            )
        except Exception:
            logger.exception("could not decrypt DocuSign token for %s", integration.id)
            return
        if not token:
            return

        payload = event.payload or {}
        recipient_email = payload.get("recipient_email") or cfg.get("default_sender_email")
        recipient_name = payload.get("recipient_name") or "Recipient"
        document_id = payload.get("document_id") or event.id
        subject = payload.get("subject") or f"Please sign: {payload.get('title', document_id)}"

        envelope = {
            "emailSubject": subject,
            "status": "sent",
            "recipients": {
                "signers": [
                    {
                        "email": recipient_email or "",
                        "name": recipient_name,
                        "recipientId": "1",
                        "routingOrder": "1",
                    }
                ]
            },
            "customFields": {
                "textCustomFields": [
                    {"name": "ec_document_id", "value": str(document_id), "show": "false"},
                    {"name": "ec_tenant_id", "value": str(integration.tenant_id), "show": "false"},
                ]
            },
        }

        url = f"{api_base}/restapi/v2.1/accounts/{account_id}/envelopes"
        client = _http_client()
        try:
            resp = client.post(
                url,
                content=json.dumps(envelope).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=10.0,
            )
        except Exception:
            logger.exception("DocuSign envelope create failed for %s", event.type)
            return
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

        if hasattr(resp, "status_code") and resp.status_code >= 400:
            logger.warning("DocuSign envelope returned %s", resp.status_code)
        _mark_used(integration)

    # ---- inbound webhook (DocuSign Connect) -----------------------------
    def handle_inbound(
        self,
        payload: dict,
        headers: dict,
        integration: TenantIntegration,
    ) -> dict | None:
        """Receive DocuSign Connect notifications. We accept the simplified
        JSON Connect payload (``envelopeId`` + ``status`` + custom fields)
        and emit ``docusign.envelope.completed`` when the envelope is
        signed.
        """
        from app.services.event_bus import publish_event

        envelope_id = payload.get("envelopeId") or (
            payload.get("data", {}).get("envelopeId") if isinstance(payload.get("data"), dict) else None
        )
        status = (payload.get("status") or payload.get("event") or "").lower()
        custom = (payload.get("customFields") or {}).get("textCustomFields") or []
        doc_id = None
        for f in custom:
            if isinstance(f, dict) and f.get("name") == "ec_document_id":
                doc_id = f.get("value")
                break

        if status in ("completed", "envelope-completed", "signed"):
            publish_event(
                "docusign.envelope.completed",
                payload={
                    "envelope_id": envelope_id,
                    "document_id": doc_id,
                    "status": "completed",
                },
                tenant_id=integration.tenant_id,
            )
            return {"ok": True, "envelope_id": envelope_id, "status": "completed"}
        return {"ok": True, "envelope_id": envelope_id, "status": status or "ignored"}
