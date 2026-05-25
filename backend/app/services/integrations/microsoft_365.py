"""Microsoft 365 integration — Calendar + Mail + SharePoint.

Shares the Azure AD app credentials with Microsoft Teams (single Azure
AD registration covers both). The two connectors are separate modules
because their scopes, default event types, and tenant config bags differ
enough that fusing them would muddle the catalog UX.

Behaviour:

* ``projects.project.created`` → create a Calendar event for kickoff.
* ``construction.milestone.upcoming`` → calendar reminder.
* ``marketing.upload`` → optional upload to a configured SharePoint
  folder (skipped silently when ``sharepoint_site_id`` is unset).

Bidirectional calendar sync (reading the user's calendar and merging into
the suite's calendar page) is deferred to v2 — write-only is enough to
prove the value for now.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
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
_DEFAULT_SCOPES = (
    "Calendars.ReadWrite Mail.Send Files.ReadWrite offline_access"
)


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
    return os.environ.get("MICROSOFT_TENANT_ID", "common") or "common"


class Microsoft365Integration(Integration):
    """Microsoft 365: Calendar + Mail + SharePoint glue via Graph."""

    key = "microsoft_365"
    name = "Microsoft 365"
    category = "calendar"
    description = (
        "Create Outlook calendar events on kickoff + milestone events, "
        "optionally sync marketing uploads to a SharePoint folder."
    )
    default_event_types = [
        "projects.project.created",
        "construction.milestone.upcoming",
        "marketing.upload",
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
            return "https://docs.microsoft.com/azure/active-directory/develop/"
        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_url,
            "response_mode": "query",
            "scope": _DEFAULT_SCOPES,
            "state": f"microsoft_365:{tenant_id}",
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

        expected_state = f"microsoft_365:{tenant_id}"
        if state != expected_state:
            raise ValidationFailed("Microsoft 365 OAuth state mismatch.")

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
                f"Microsoft 365 OAuth failed: {data.get('error', 'no access_token')}"
            )
        config = {
            "default_calendar_id": "primary",
            "sharepoint_site_id": None,
            "sync_calendar_enabled": True,
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
        enabled = cfg.get("event_filter") or self.default_event_types
        if not _event_matches(event.type, enabled):
            return

        try:
            token = decrypt_field(
                integration.access_token_encrypted or "",
                integration.tenant_id,
                db=None,
            )
        except Exception:
            logger.exception("could not decrypt M365 token for %s", integration.id)
            return
        if not token:
            return

        try:
            if event.type in (
                "projects.project.created",
                "construction.milestone.upcoming",
            ):
                if not cfg.get("sync_calendar_enabled", True):
                    return
                _create_calendar_event(token, cfg, event)
            elif event.type == "marketing.upload":
                site_id = cfg.get("sharepoint_site_id")
                if not site_id:
                    logger.info(
                        "M365 SharePoint upload skipped — no site configured for tenant %s",
                        integration.tenant_id,
                    )
                    return
                _upload_to_sharepoint(token, cfg, event)
        except Exception:
            logger.exception("M365 Graph call failed for event %s", event.type)
            return

        _mark_used(integration)


def _create_calendar_event(token: str, cfg: dict, event: "Event") -> None:
    """POST a calendar event to Graph's /me/events endpoint."""
    cal_id = cfg.get("default_calendar_id") or "primary"
    if cal_id == "primary":
        url = f"{_GRAPH_BASE}/me/events"
    else:
        url = f"{_GRAPH_BASE}/me/calendars/{cal_id}/events"

    payload = event.payload or {}
    when_str = payload.get("kickoff_at") or payload.get("due_at")
    try:
        start = datetime.fromisoformat(when_str) if when_str else event.occurred_at
    except Exception:
        start = event.occurred_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    end = start + timedelta(hours=1)

    body = {
        "subject": payload.get("title", event.type),
        "body": {"contentType": "text", "content": payload.get("description", "")},
        "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
    }
    client = _http_client()
    try:
        client.post(
            url,
            content=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def _upload_to_sharepoint(token: str, cfg: dict, event: "Event") -> None:
    """PUT the asset bytes to a SharePoint drive folder.

    Marketing uploads carry a ``filename`` + ``content_base64`` in the
    event payload — keeping the surface synchronous and small avoids
    pulling in the Graph SDK.
    """
    import base64

    site_id = cfg.get("sharepoint_site_id")
    payload = event.payload or {}
    filename = payload.get("filename") or f"{event.id}.bin"
    encoded = payload.get("content_base64") or ""
    if not encoded:
        return
    try:
        content = base64.b64decode(encoded)
    except Exception:
        logger.warning("M365 SharePoint upload: payload content_base64 invalid")
        return

    url = f"{_GRAPH_BASE}/sites/{site_id}/drive/root:/{filename}:/content"
    client = _http_client()
    try:
        client.post(
            url,
            content=content,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/octet-stream",
            },
            timeout=30.0,
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
