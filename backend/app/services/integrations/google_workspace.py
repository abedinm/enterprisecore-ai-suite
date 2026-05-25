"""Google Workspace integration — Calendar + Drive Sheets.

OAuth scopes:

* ``calendar.events`` — create kickoff + milestone reminders
* ``drive.file`` — append a row to a task-completion log spreadsheet

The google-api-python-client + google-auth libraries are *optional*
dependencies. The OAuth dance + endpoint surface works without them,
but the actual API calls degrade gracefully: a missing library logs a
warning and skips the call. Customers who want full Workspace
functionality install ``requirements-integrations.txt``.

Workspace OAuth credentials (``GOOGLE_CLIENT_ID`` / ``GOOGLE_CLIENT_SECRET``)
are deployment-owned, mirroring the Slack pattern.
"""
from __future__ import annotations

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
    _delete_integration, _event_matches, _upsert_integration,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.services.event_bus import Event

logger = logging.getLogger(__name__)


_OAUTH_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
_OAUTH_TOKEN = "https://oauth2.googleapis.com/token"
_DEFAULT_SCOPES = (
    "https://www.googleapis.com/auth/calendar.events "
    "https://www.googleapis.com/auth/drive.file"
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


class GoogleWorkspaceIntegration(Integration):
    """Google Workspace: drop task-completion rows into a Drive Sheet +
    create calendar events for project milestones."""

    key = "google_workspace"
    name = "Google Workspace"
    category = "calendar"
    description = (
        "Mirror project + task activity into Google Calendar and Drive Sheets."
    )
    default_event_types = [
        "projects.task.completed",
        "projects.project.created",
        "construction.milestone.upcoming",
    ]

    @classmethod
    def is_configurable(cls) -> bool:
        return bool(os.environ.get("GOOGLE_CLIENT_ID")) and bool(
            os.environ.get("GOOGLE_CLIENT_SECRET")
        )

    # ---- install / OAuth ------------------------------------------------
    def install_url(self, tenant_id: str, redirect_url: str) -> str:
        client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        if not client_id:
            raise ValidationFailed("GOOGLE_CLIENT_ID is not configured on this deployment.")
        params = {
            "client_id": client_id,
            "scope": _DEFAULT_SCOPES,
            "response_type": "code",
            "redirect_uri": redirect_url,
            "access_type": "offline",
            "prompt": "consent",
            "state": f"google_workspace:{tenant_id}",
        }
        return f"{_OAUTH_AUTHORIZE}?{urlencode(params)}"

    def handle_oauth_callback(
        self,
        tenant_id: str,
        code: str,
        state: str,
        db: Session,
    ) -> TenantIntegration:
        client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            raise ValidationFailed("Google OAuth credentials are not configured.")

        expected_state = f"google_workspace:{tenant_id}"
        if state != expected_state:
            raise ValidationFailed("Google OAuth state mismatch.")

        redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "")
        client = _http_client()
        try:
            resp = client.post(
                _OAUTH_TOKEN,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
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
                f"Google OAuth failed: {data.get('error', 'no access_token')}"
            )
        refresh_token = data.get("refresh_token")
        expires_in = int(data.get("expires_in") or 0)
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            if expires_in
            else None
        )
        config = {
            "target_calendar_id": "primary",
            "target_drive_folder_id": None,
            "enabled_events": list(self.default_event_types),
            "scopes_granted": data.get("scope", _DEFAULT_SCOPES),
        }
        return _upsert_integration(
            db,
            tenant_id=tenant_id,
            key=self.key,
            name=self.name,
            access_token=access_token,
            refresh_token=refresh_token or "",
            token_expires_at=expires_at,
            config=config,
        )

    def uninstall(self, tenant_id: str, db: Session) -> None:
        _delete_integration(db, tenant_id, self.key)

    # ---- event handling -------------------------------------------------
    def handle_event(self, event: "Event", integration: TenantIntegration) -> None:
        if not integration.is_enabled:
            return
        cfg = integration.config or {}
        enabled = cfg.get("enabled_events") or self.default_event_types
        if not _event_matches(event.type, enabled):
            return

        try:
            token = decrypt_field(
                integration.access_token_encrypted or "",
                integration.tenant_id,
                db=None,
            )
        except Exception:
            logger.exception("could not decrypt google token for %s", integration.id)
            return
        if not token:
            return

        try:
            if event.type == "projects.task.completed":
                _append_to_sheet(token, cfg, event)
            elif event.type in (
                "projects.project.created",
                "construction.milestone.upcoming",
            ):
                _create_calendar_event(token, cfg, event)
        except _GoogleLibMissing:
            logger.warning(
                "google-api-python-client not installed — skipping Google call for %s",
                event.type,
            )
        except Exception:
            logger.exception("Google API call failed for event %s", event.type)


# ---------------------------------------------------------------------------
# google-api-python-client interop. Wrapped so a missing library degrades
# gracefully — we log + skip rather than crash the event bus.
# ---------------------------------------------------------------------------
class _GoogleLibMissing(Exception):
    """Raised when google-api-python-client isn't installed."""


def _google_service(api: str, version: str, token: str):
    try:
        from googleapiclient.discovery import build  # type: ignore
        from google.oauth2.credentials import Credentials  # type: ignore
    except ImportError as exc:
        raise _GoogleLibMissing() from exc

    creds = Credentials(token=token)
    return build(api, version, credentials=creds, cache_discovery=False)


def _append_to_sheet(token: str, cfg: dict, event: "Event") -> None:
    """Append one row to a Sheet for each completed task."""
    sheet_id = cfg.get("target_drive_folder_id")  # we reuse this slot for sheet id
    if not sheet_id:
        logger.info("Google integration has no target sheet configured; skipping")
        return
    service = _google_service("sheets", "v4", token)
    row = [
        event.occurred_at.isoformat(),
        event.payload.get("task_id", ""),
        event.payload.get("title", ""),
        event.payload.get("project", ""),
        event.payload.get("completed_by", ""),
    ]
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="A:E",
        valueInputOption="USER_ENTERED",
        body={"values": [row]},
    ).execute()


def _create_calendar_event(token: str, cfg: dict, event: "Event") -> None:
    """Create a calendar event for a project kickoff or milestone."""
    cal_id = cfg.get("target_calendar_id") or "primary"
    service = _google_service("calendar", "v3", token)

    when_str = event.payload.get("kickoff_at") or event.payload.get("due_at")
    try:
        start = datetime.fromisoformat(when_str) if when_str else event.occurred_at
    except Exception:
        start = event.occurred_at
    end = start + timedelta(hours=1)

    body = {
        "summary": event.payload.get("title", event.type),
        "description": event.payload.get("description", ""),
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    service.events().insert(calendarId=cal_id, body=body).execute()
