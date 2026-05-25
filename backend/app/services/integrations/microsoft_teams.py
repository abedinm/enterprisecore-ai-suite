"""Microsoft Teams integration — Graph API channel-message posting.

Auth uses the Microsoft identity platform (Azure AD v2.0). The deployment
owns a single multi-tenant Azure AD app and supplies its credentials via
``MICROSOFT_CLIENT_ID`` / ``MICROSOFT_CLIENT_SECRET`` / ``MICROSOFT_TENANT_ID``.
Each EnterpriseCore tenant installs the same Azure AD app — the per-tenant
Teams `team_id` / `channel_id` live in the integration config row.

Why a separate connector from Microsoft 365 even though they share the
Azure AD app? Different scopes, different default events, and the UI
catalog renders them as distinct line items — keeping the modules apart
matches the Slack/Google split.
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


_AUTHORITY_BASE = "https://login.microsoftonline.com"
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_DEFAULT_SCOPES = "ChannelMessage.Send Team.ReadBasic.All offline_access"


_http_client_factory = None


def set_http_client_factory(factory):
    """Tests use this to substitute a fake httpx client."""
    global _http_client_factory
    _http_client_factory = factory


def _http_client():
    if _http_client_factory is not None:
        return _http_client_factory()
    return httpx.Client(timeout=10.0)


def _tenant_segment() -> str:
    """Return the Azure AD tenant segment for the token endpoint.

    Falls back to ``common`` when ``MICROSOFT_TENANT_ID`` isn't set, which
    is the right value for a multi-tenant app accepting any work/school
    account. Single-tenant deployments override with their directory GUID.
    """
    return os.environ.get("MICROSOFT_TENANT_ID", "common") or "common"


class MicrosoftTeamsIntegration(Integration):
    """Microsoft Teams connector — channel-message poster."""

    key = "microsoft_teams"
    name = "Microsoft Teams"
    category = "messaging"
    description = (
        "Post deal wins, new leads, paid invoices, and risk alerts to a "
        "Teams channel via the Graph API."
    )
    default_event_types = [
        "crm.deal.won",
        "crm.lead.created",
        "finance.invoice.paid",
        "construction.risk.created",
    ]

    @classmethod
    def is_configurable(cls) -> bool:
        return bool(os.environ.get("MICROSOFT_CLIENT_ID")) and bool(
            os.environ.get("MICROSOFT_CLIENT_SECRET")
        )

    # ---- install / OAuth ------------------------------------------------
    def install_url(self, tenant_id: str, redirect_url: str) -> str:
        client_id = os.environ.get("MICROSOFT_CLIENT_ID", "")
        if not client_id:
            # Graceful: return a docs link so the catalog page can still
            # render a useful button instead of throwing.
            return "https://docs.microsoft.com/azure/active-directory/develop/"
        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_url,
            "response_mode": "query",
            "scope": _DEFAULT_SCOPES,
            "state": f"microsoft_teams:{tenant_id}",
        }
        return f"{_AUTHORITY_BASE}/{_tenant_segment()}/oauth2/v2.0/authorize?{urlencode(params)}"

    def handle_oauth_callback(
        self,
        tenant_id: str,
        code: str,
        state: str,
        db: Session,
    ) -> TenantIntegration:
        client_id = os.environ.get("MICROSOFT_CLIENT_ID", "")
        client_secret = os.environ.get("MICROSOFT_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            raise ValidationFailed("Microsoft OAuth credentials are not configured.")

        expected_state = f"microsoft_teams:{tenant_id}"
        if state != expected_state:
            raise ValidationFailed("Microsoft Teams OAuth state mismatch.")

        redirect_uri = os.environ.get("MICROSOFT_REDIRECT_URI", "")
        token_url = f"{_AUTHORITY_BASE}/{_tenant_segment()}/oauth2/v2.0/token"
        client = _http_client()
        try:
            resp = client.post(
                token_url,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                    "scope": _DEFAULT_SCOPES,
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
                f"Microsoft Teams OAuth failed: {data.get('error', 'no access_token')}"
            )
        config = {
            "team_id": None,
            "channel_id": None,
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

        team_id = cfg.get("team_id")
        channel_id = cfg.get("channel_id")
        if not team_id or not channel_id:
            logger.info(
                "Teams integration %s has no team/channel configured; skipping",
                integration.id,
            )
            return

        text = _render_message(event)
        if not text:
            return

        try:
            token = decrypt_field(
                integration.access_token_encrypted or "",
                integration.tenant_id,
                db=None,
            )
        except Exception:
            logger.exception("could not decrypt Teams token for %s", integration.id)
            return
        if not token:
            logger.warning("Teams integration %s has no token", integration.id)
            return

        url = f"{_GRAPH_BASE}/teams/{team_id}/channels/{channel_id}/messages"
        body = {"body": {"contentType": "html", "content": text}}
        client = _http_client()
        try:
            resp = client.post(
                url,
                content=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                timeout=10.0,
            )
        except Exception:
            logger.exception("Teams Graph POST failed for %s", event.type)
            return
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

        if hasattr(resp, "status_code") and resp.status_code >= 400:
            logger.warning("Teams Graph POST returned %s", resp.status_code)
        _mark_used(integration)


def _render_message(event: "Event") -> str:
    """Render an HTML-ready Teams message for known event types."""
    p = event.payload or {}
    if event.type == "crm.deal.won":
        return f"<b>Deal won:</b> {p.get('name', 'Deal')} for ${p.get('amount', '0')}"
    if event.type == "crm.lead.created":
        return f"<b>New lead:</b> {p.get('name', 'Lead')} from {p.get('source', 'unknown')}"
    if event.type == "finance.invoice.paid":
        return (
            f"<b>Invoice {p.get('number', '')} paid</b> by "
            f"{p.get('customer', 'customer')} (${p.get('amount', '0')})"
        )
    if event.type == "construction.risk.created":
        sev = p.get("severity", "medium")
        return (
            f"<b>[{sev.upper()}]</b> New risk on {p.get('project', 'project')}: "
            f"{p.get('title', 'Risk logged')}"
        )
    if event.type == "webhook.test":
        return "Test event from EnterpriseCore — Microsoft Teams is wired up."
    return ""
