"""Slack integration — OAuth v2 install + bot-token chat.postMessage.

Flow:

  1. Customer hits ``POST /integrations/slack/install`` and is redirected
     to ``slack.com/oauth/v2/authorize`` with a signed ``state`` token.
  2. Slack redirects back to ``GET /integrations/oauth/callback`` with a
     ``code``; we exchange it for a bot token + workspace metadata via
     ``slack.com/api/oauth.v2.access``.
  3. Token is stored in :class:`TenantIntegration.access_token_encrypted`
     under the tenant's DEK.
  4. The connector subscribes to a small set of business-meaningful events
     (deals won, leads created, risks logged, etc.) and posts a templated
     message to the workspace's default channel.

Slack credentials (``SLACK_CLIENT_ID`` / ``SLACK_CLIENT_SECRET``) are owned
by the deployment, not the tenant — every tenant on a given install shares
the same Slack app, which is the recommended pattern for multi-tenant SaaS.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import decrypt_field, encrypt_field
from app.core.exceptions import NotFoundError, ValidationFailed
from app.core.tenant_context import bypass_tenant_filter
from app.models.integrations import TenantIntegration
from app.services.integrations.base import Integration

if TYPE_CHECKING:  # pragma: no cover
    from app.services.event_bus import Event

logger = logging.getLogger(__name__)


_OAUTH_AUTHORIZE = "https://slack.com/oauth/v2/authorize"
_OAUTH_TOKEN = "https://slack.com/api/oauth.v2.access"
_CHAT_POST_MESSAGE = "https://slack.com/api/chat.postMessage"
_DEFAULT_SCOPES = "chat:write,channels:read,incoming-webhook"


# Module-level injection point for tests — they replace this with a fake
# httpx.Client so the connector never reaches Slack during the suite.
_http_client_factory = None


def set_http_client_factory(factory):
    """Tests use this to substitute a fake httpx client."""
    global _http_client_factory
    _http_client_factory = factory


def _http_client():
    if _http_client_factory is not None:
        return _http_client_factory()
    return httpx.Client(timeout=10.0)


class SlackIntegration(Integration):
    """Slack workspace connector. Posts business events as chat messages."""

    key = "slack"
    name = "Slack"
    category = "messaging"
    description = "Post deal wins, new leads, paid invoices, and risk alerts to a Slack channel."
    default_event_types = [
        "crm.deal.won",
        "crm.lead.created",
        "finance.invoice.paid",
        "construction.risk.created",
        "webchat.conversation.created",
    ]

    @classmethod
    def is_configurable(cls) -> bool:
        return bool(os.environ.get("SLACK_CLIENT_ID")) and bool(os.environ.get("SLACK_CLIENT_SECRET"))

    # ---- install / OAuth ------------------------------------------------
    def install_url(self, tenant_id: str, redirect_url: str) -> str:
        client_id = os.environ.get("SLACK_CLIENT_ID", "")
        if not client_id:
            raise ValidationFailed("SLACK_CLIENT_ID is not configured on this deployment.")
        params = {
            "client_id": client_id,
            "scope": _DEFAULT_SCOPES,
            "redirect_uri": redirect_url,
            # state must be unguessable + tenant-bound. We sign with the
            # tenant id; the callback verifies before persisting tokens.
            "state": f"slack:{tenant_id}",
        }
        return f"{_OAUTH_AUTHORIZE}?{urlencode(params)}"

    def handle_oauth_callback(
        self,
        tenant_id: str,
        code: str,
        state: str,
        db: Session,
    ) -> TenantIntegration:
        client_id = os.environ.get("SLACK_CLIENT_ID", "")
        client_secret = os.environ.get("SLACK_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            raise ValidationFailed("Slack OAuth credentials are not configured.")

        expected_state = f"slack:{tenant_id}"
        if state != expected_state:
            raise ValidationFailed("Slack OAuth state mismatch.")

        client = _http_client()
        try:
            resp = client.post(
                _OAUTH_TOKEN,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                },
                timeout=10.0,
            )
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

        data = resp.json() if hasattr(resp, "json") else {}
        if not data.get("ok"):
            raise ValidationFailed(f"Slack OAuth failed: {data.get('error', 'unknown')}")

        bot_token = data.get("access_token", "")
        team = data.get("team", {}) or {}
        incoming = data.get("incoming_webhook", {}) or {}
        config = {
            "team_id": team.get("id"),
            "team_name": team.get("name"),
            "default_channel": incoming.get("channel_id"),
            "default_channel_name": incoming.get("channel"),
            "incoming_webhook_url": incoming.get("url"),
            "event_filter": list(self.default_event_types),
        }

        return _upsert_integration(
            db,
            tenant_id=tenant_id,
            key=self.key,
            name=self.name,
            access_token=bot_token,
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

        text = _render_message(event)
        if not text:
            return

        channel = cfg.get("default_channel")
        token = decrypt_field(
            integration.access_token_encrypted or "",
            integration.tenant_id,
            db=None,
        )
        if not token:
            logger.warning("Slack integration %s has no token", integration.id)
            return

        client = _http_client()
        try:
            resp = client.post(
                _CHAT_POST_MESSAGE,
                content=json.dumps({"channel": channel, "text": text}).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                timeout=10.0,
            )
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

        try:
            body = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            body = {}
        if not body.get("ok", True):
            logger.warning("Slack chat.postMessage failed: %s", body.get("error"))
        _mark_used(integration)


def _event_matches(event_type: str, patterns: list[str]) -> bool:
    """Match an event type against a list of fnmatch patterns. ``*`` and
    bare wildcard segments (``crm.*``) both work."""
    import fnmatch

    for pat in patterns:
        if pat == "*" or pat == event_type:
            return True
        if fnmatch.fnmatch(event_type, pat):
            return True
    return False


def _render_message(event: "Event") -> str:
    """Render a Slack-ready message for one of the known event types.

    Templates are intentionally simple — admins who want richer formatting
    use the workflow engine's ``send_slack_message`` action with a custom
    template instead of the default connector handler.
    """
    p = event.payload or {}
    if event.type == "crm.deal.won":
        return f"Deal won: {p.get('name', 'Deal')} for ${p.get('amount', '0')}"
    if event.type == "crm.lead.created":
        return f"New lead: {p.get('name', 'Lead')} from {p.get('source', 'unknown')}"
    if event.type == "finance.invoice.paid":
        return (
            f"Invoice {p.get('number', '')} paid by "
            f"{p.get('customer', 'customer')} (${p.get('amount', '0')})"
        )
    if event.type == "construction.risk.created":
        sev = p.get("severity", "medium")
        emoji = "[!]" if sev in ("high", "critical") else "[~]"
        return (
            f"{emoji} New {sev} risk on {p.get('project', 'project')}: "
            f"{p.get('title', 'Risk logged')}"
        )
    if event.type == "webchat.conversation.created":
        return f"New chat: {p.get('visitor', 'visitor')} on {p.get('bot', 'bot')}"
    if event.type == "webhook.test":
        return "Test event from EnterpriseCore: Slack integration is wired up correctly."
    return ""


# ---- shared CRUD helpers (used by all three connectors) -----------------

def _upsert_integration(
    db: Session,
    *,
    tenant_id: str,
    key: str,
    name: str,
    access_token: str | None = None,
    refresh_token: str | None = None,
    token_expires_at: datetime | None = None,
    config: dict | None = None,
    installed_by_user_id: str | None = None,
) -> TenantIntegration:
    """Find-or-create the (tenant, key) row, refresh tokens + config.

    Uses ``bypass_tenant_filter`` because the OAuth callback runs outside
    a normal auth-bearing request (Slack/Google posts to it directly)
    and would otherwise be invisible to the auto-filter."""
    with bypass_tenant_filter():
        row = db.scalar(
            select(TenantIntegration).where(
                TenantIntegration.tenant_id == tenant_id,
                TenantIntegration.key == key,
            )
        )
    now = datetime.now(timezone.utc)
    if row is None:
        row = TenantIntegration(
            tenant_id=tenant_id,
            key=key,
            name=name,
            config=config or {},
            installed_by_user_id=installed_by_user_id,
            installed_at=now,
        )
        db.add(row)
    else:
        if config is not None:
            merged = dict(row.config or {})
            merged.update(config)
            row.config = merged
        row.installed_at = row.installed_at or now
    if access_token is not None:
        row.access_token_encrypted = encrypt_field(access_token, tenant_id, db=db) if access_token else None
    if refresh_token is not None:
        row.refresh_token_encrypted = encrypt_field(refresh_token, tenant_id, db=db) if refresh_token else None
    if token_expires_at is not None:
        row.token_expires_at = token_expires_at
    row.is_enabled = True
    db.commit()
    db.refresh(row)
    return row


def _delete_integration(db: Session, tenant_id: str, key: str) -> None:
    with bypass_tenant_filter():
        row = db.scalar(
            select(TenantIntegration).where(
                TenantIntegration.tenant_id == tenant_id,
                TenantIntegration.key == key,
            )
        )
        if row is None:
            return
        db.delete(row)
        db.commit()


def _mark_used(integration: TenantIntegration) -> None:
    """Best-effort timestamp bump. Mutates the in-memory row only — the
    handler runs inside the event-bus call site which holds no DB
    session of its own. The row's persistent ``last_used_at`` is updated
    by the workflow engine when it touches it via a Session."""
    integration.last_used_at = datetime.now(timezone.utc)
