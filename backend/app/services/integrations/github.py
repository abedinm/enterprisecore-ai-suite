"""GitHub integration — connect repos for the AI Coding module.

OAuth (web flow):

  1. Customer hits ``POST /integrations/github/install`` and is sent to
     ``github.com/login/oauth/authorize``.
  2. GitHub redirects back with a ``code``; we exchange via
     ``github.com/login/oauth/access_token`` for a bearer token.
  3. The token is stored under the tenant DEK.
  4. The connector subscribes to ``coding.repo.connected`` — when the
     coding module emits the event we hit the GitHub API to fetch the
     repo's default branch + clone URL and stash them in the config bag.
  5. ``POST /api/v1/integrations/github/inbound`` accepts GitHub webhook
     deliveries (issue events) and emits ``github.issue.opened`` /
     ``github.issue.closed`` for downstream workflows (the CRM follow-up
     creation is out of scope for v1).
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


_OAUTH_AUTHORIZE = "https://github.com/login/oauth/authorize"
_OAUTH_TOKEN = "https://github.com/login/oauth/access_token"
_API_BASE = "https://api.github.com"
_DEFAULT_SCOPES = "repo read:user read:org"


_http_client_factory = None


def set_http_client_factory(factory):
    """Tests use this to substitute a fake httpx client."""
    global _http_client_factory
    _http_client_factory = factory


def _http_client():
    if _http_client_factory is not None:
        return _http_client_factory()
    return httpx.Client(timeout=10.0)


class GitHubIntegration(Integration):
    """GitHub repo connector for the AI Coding module."""

    key = "github"
    name = "GitHub"
    category = "developer"
    description = (
        "Connect GitHub repositories so the AI Coding module can track "
        "issues + PRs. Inbound webhooks emit issue events."
    )
    default_event_types = ["coding.repo.connected"]

    @classmethod
    def is_configurable(cls) -> bool:
        return bool(os.environ.get("GITHUB_CLIENT_ID")) and bool(
            os.environ.get("GITHUB_CLIENT_SECRET")
        )

    # ---- install / OAuth ------------------------------------------------
    def install_url(self, tenant_id: str, redirect_url: str) -> str:
        client_id = os.environ.get("GITHUB_CLIENT_ID", "")
        if not client_id:
            return "https://docs.github.com/en/apps/oauth-apps"
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_url,
            "scope": _DEFAULT_SCOPES,
            "state": f"github:{tenant_id}",
            "allow_signup": "false",
        }
        return f"{_OAUTH_AUTHORIZE}?{urlencode(params)}"

    def handle_oauth_callback(
        self,
        tenant_id: str,
        code: str,
        state: str,
        db: Session,
    ) -> TenantIntegration:
        client_id = os.environ.get("GITHUB_CLIENT_ID", "")
        client_secret = os.environ.get("GITHUB_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            raise ValidationFailed("GitHub OAuth credentials are not configured.")

        expected_state = f"github:{tenant_id}"
        if state != expected_state:
            raise ValidationFailed("GitHub OAuth state mismatch.")

        client = _http_client()
        try:
            resp = client.post(
                _OAUTH_TOKEN,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                },
                headers={"Accept": "application/json"},
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
                f"GitHub OAuth failed: {data.get('error', 'no access_token')}"
            )
        config = {
            "default_organization": "",
            "connected_repos": [],
            "scopes_granted": data.get("scope", _DEFAULT_SCOPES),
            "event_filter": list(self.default_event_types),
        }
        return _upsert_integration(
            db,
            tenant_id=tenant_id,
            key=self.key,
            name=self.name,
            access_token=access_token,
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

        try:
            token = decrypt_field(
                integration.access_token_encrypted or "",
                integration.tenant_id,
                db=None,
            )
        except Exception:
            logger.exception("could not decrypt GitHub token for %s", integration.id)
            return
        if not token:
            return

        if event.type == "coding.repo.connected":
            _enrich_repo(token, cfg, event, integration)
            _mark_used(integration)

    # ---- inbound webhook ------------------------------------------------
    def handle_inbound(
        self,
        payload: dict,
        headers: dict,
        integration: TenantIntegration,
    ) -> dict | None:
        """Handle GitHub webhook deliveries. We only act on ``issues`` for
        v1 — emit ``github.issue.opened`` / ``github.issue.closed`` events
        on the local bus, which downstream workflows can subscribe to.
        """
        from app.services.event_bus import publish_event

        # GitHub identifies the event via the X-GitHub-Event header; fall
        # back to the payload's ``action`` field for legacy callers.
        event_kind = (headers.get("X-GitHub-Event") or headers.get("x-github-event") or "").lower()
        action = (payload.get("action") or "").lower()

        if event_kind == "issues" and action in ("opened", "closed", "reopened"):
            issue = payload.get("issue") or {}
            repo = payload.get("repository") or {}
            published = publish_event(
                f"github.issue.{action}",
                payload={
                    "issue_number": issue.get("number"),
                    "title": issue.get("title"),
                    "url": issue.get("html_url"),
                    "repo": repo.get("full_name"),
                    "assignee": (issue.get("assignee") or {}).get("login"),
                },
                tenant_id=integration.tenant_id,
            )
            return {"ok": True, "event_id": published.id, "action": action}
        if event_kind == "ping":
            return {"ok": True, "pong": True}
        return {"ok": True, "event": event_kind, "action": action or "ignored"}


def _enrich_repo(
    token: str,
    cfg: dict,
    event: "Event",
    integration: TenantIntegration,
) -> None:
    """When a repo is connected, fetch its metadata from GitHub and
    append it to ``connected_repos`` in the integration config.

    We keep this side-effect to the in-memory row only — the workflow
    engine or endpoint handler is responsible for persisting config
    changes via a Session.
    """
    full_name = (event.payload or {}).get("repo")
    if not full_name:
        return
    url = f"{_API_BASE}/repos/{full_name}"
    client = _http_client()
    try:
        resp = client.get(  # type: ignore[attr-defined]
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10.0,
        )
    except AttributeError:
        # Fake client may not implement .get — treat as a no-op fetch.
        return
    except Exception:
        logger.exception("GitHub repo fetch failed for %s", full_name)
        return
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    data = resp.json() if hasattr(resp, "json") else {}
    repos = list(cfg.get("connected_repos") or [])
    repos.append({
        "full_name": data.get("full_name", full_name),
        "default_branch": data.get("default_branch", "main"),
        "clone_url": data.get("clone_url"),
        "private": data.get("private", False),
    })
    cfg["connected_repos"] = repos
