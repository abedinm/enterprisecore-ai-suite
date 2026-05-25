"""Slack integration tests — OAuth flow, event handling, cross-tenant isolation."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter
from app.models.integrations import TenantIntegration
from app.services.event_bus import publish_event, reset_subscribers
from app.services.integrations import register_all_subscribers
from app.services.integrations import slack as slack_mod


class _FakeResp:
    def __init__(self, status_code=200, data=None, text=""):
        self.status_code = status_code
        self._data = data or {}
        self.text = text

    def json(self):
        return self._data


class _FakeHttp:
    """In-memory httpx replacement. Each instance records every POST so
    tests can assert on URL + headers + body. Configure responses via the
    ``responses`` dict keyed by URL (or default ``ok=True``)."""

    instances: list = []
    responses: dict[str, dict] = {}

    def __init__(self):
        self.posts: list[dict] = []
        _FakeHttp.instances.append(self)

    def post(self, url, content=None, data=None, headers=None, timeout=None):
        self.posts.append({
            "url": url, "content": content, "data": data,
            "headers": dict(headers or {}),
        })
        cfg = _FakeHttp.responses.get(url, {"ok": True})
        if cfg.get("status_code"):
            return _FakeResp(status_code=cfg["status_code"], data=cfg.get("data", {}))
        return _FakeResp(data=cfg)

    def close(self):
        pass


@pytest.fixture()
def fake_http(monkeypatch):
    _FakeHttp.instances.clear()
    _FakeHttp.responses.clear()
    slack_mod.set_http_client_factory(lambda: _FakeHttp())
    # Also patch the workflow engine which uses the same module-level factory.
    yield _FakeHttp
    slack_mod.set_http_client_factory(None)


@pytest.fixture(autouse=True)
def _wipe(monkeypatch):
    """Reset event subscribers + slack rows between tests."""
    monkeypatch.setenv("SLACK_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "test-client-secret")
    reset_subscribers()
    register_all_subscribers()
    from app.db.session import SessionLocal

    with SessionLocal() as db, bypass_tenant_filter():
        db.query(TenantIntegration).delete()
        db.commit()
    yield
    reset_subscribers()
    with SessionLocal() as db, bypass_tenant_filter():
        db.query(TenantIntegration).delete()
        db.commit()


def test_install_url_includes_oauth_params(client, auth_headers):
    r = client.post("/api/v1/integrations/slack/install", headers=auth_headers)
    assert r.status_code == 200, r.text
    url = r.json()["install_url"]
    assert url.startswith("https://slack.com/oauth/v2/authorize")
    assert "client_id=test-client-id" in url
    assert "scope=chat" in url
    assert "state=slack" in url


def test_oauth_callback_persists_tokens(client, auth_headers, fake_http, db):
    # Pre-arrange the fake Slack token endpoint response.
    _FakeHttp.responses["https://slack.com/api/oauth.v2.access"] = {
        "ok": True,
        "access_token": "xoxb-test-token",
        "team": {"id": "T1", "name": "Test Team"},
        "incoming_webhook": {
            "channel": "#general",
            "channel_id": "C1",
            "url": "https://hooks.slack.com/test",
        },
    }
    tenant_id = db.scalar(select(TenantIntegration).limit(1))
    # No row yet — fetch the default tenant via a known query.
    from app.models.tenant import Tenant
    tenant = db.scalar(select(Tenant).limit(1))
    assert tenant is not None

    r = client.get(
        f"/api/v1/integrations/oauth/callback?key=slack&code=abc&state=slack:{tenant.id}",
    )
    assert r.status_code == 200, r.text
    row = db.scalar(select(TenantIntegration).where(TenantIntegration.key == "slack"))
    assert row is not None
    assert row.access_token_encrypted
    assert row.access_token_encrypted.startswith("v")
    assert row.config["team_id"] == "T1"


def test_event_handling_posts_to_slack(client, auth_headers, fake_http, db):
    """A crm.deal.won event should POST to chat.postMessage with a bot token."""
    _FakeHttp.responses["https://slack.com/api/oauth.v2.access"] = {
        "ok": True,
        "access_token": "xoxb-bot-token",
        "team": {"id": "T1"},
        "incoming_webhook": {"channel_id": "C1", "channel": "#sales"},
    }
    from app.models.tenant import Tenant
    tenant = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=slack&code=abc&state=slack:{tenant.id}"
    )
    _FakeHttp.instances.clear()  # forget the OAuth POST

    publish_event(
        "crm.deal.won",
        payload={"name": "Acme Corp", "amount": 50000},
        tenant_id=tenant.id,
    )
    posts = [p for inst in _FakeHttp.instances for p in inst.posts]
    chat_posts = [p for p in posts if p["url"].endswith("chat.postMessage")]
    assert len(chat_posts) == 1
    body = json.loads(chat_posts[0]["content"].decode())
    assert body["channel"] == "C1"
    assert "Acme Corp" in body["text"]
    assert chat_posts[0]["headers"]["Authorization"] == "Bearer xoxb-bot-token"


def test_uninstall_clears_row(client, auth_headers, fake_http, db):
    _FakeHttp.responses["https://slack.com/api/oauth.v2.access"] = {
        "ok": True,
        "access_token": "xoxb-token",
        "team": {"id": "T1"},
        "incoming_webhook": {"channel_id": "C1"},
    }
    from app.models.tenant import Tenant
    tenant = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=slack&code=x&state=slack:{tenant.id}"
    )
    assert db.scalar(select(TenantIntegration).where(TenantIntegration.key == "slack")) is not None

    r = client.post("/api/v1/integrations/slack/uninstall", headers=auth_headers)
    assert r.status_code == 204
    db.expire_all()
    assert db.scalar(select(TenantIntegration).where(TenantIntegration.key == "slack")) is None


def test_cross_tenant_isolation(client, auth_headers, fake_http, db, make_tenant):
    """Tenant A installing Slack must not leak into tenant B's installed list."""
    _FakeHttp.responses["https://slack.com/api/oauth.v2.access"] = {
        "ok": True,
        "access_token": "xoxb-A",
        "team": {"id": "T-A"},
        "incoming_webhook": {"channel_id": "C-A"},
    }
    from app.models.tenant import Tenant
    tenant_a = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=slack&code=x&state=slack:{tenant_a.id}"
    )

    tenant_b, _user_b, token_b = make_tenant("slack-iso-b")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    r = client.get("/api/v1/integrations/installed", headers=headers_b)
    assert r.status_code == 200
    keys = [row["key"] for row in r.json()]
    assert "slack" not in keys
