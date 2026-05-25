"""Microsoft Teams integration tests."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter
from app.models.integrations import TenantIntegration
from app.models.tenant import Tenant
from app.services.event_bus import publish_event, reset_subscribers
from app.services.integrations import register_all_subscribers
from app.services.integrations import microsoft_teams as teams_mod


class _FakeResp:
    def __init__(self, data=None, status_code=200):
        self._data = data or {}
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._data


class _FakeHttp:
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
        return _FakeResp(_FakeHttp.responses.get(url, {}))

    def close(self):
        pass


@pytest.fixture()
def fake_http():
    _FakeHttp.instances.clear()
    _FakeHttp.responses.clear()
    teams_mod.set_http_client_factory(lambda: _FakeHttp())
    yield _FakeHttp
    teams_mod.set_http_client_factory(None)


@pytest.fixture(autouse=True)
def _wipe(monkeypatch):
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "ms-test-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "ms-test-secret")
    monkeypatch.setenv("MICROSOFT_TENANT_ID", "common")
    monkeypatch.setenv("MICROSOFT_REDIRECT_URI", "https://example.test/cb")
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


def test_install_url_uses_microsoft_authorize(client, auth_headers):
    r = client.post("/api/v1/integrations/microsoft_teams/install", headers=auth_headers)
    assert r.status_code == 200, r.text
    url = r.json()["install_url"]
    assert url.startswith("https://login.microsoftonline.com/")
    assert "client_id=ms-test-id" in url
    assert "ChannelMessage.Send" in url or "ChannelMessage" in url


def test_callback_persists_token(client, auth_headers, fake_http, db):
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    _FakeHttp.responses[token_url] = {
        "access_token": "ms-graph-token",
        "refresh_token": "ms-refresh",
        "expires_in": 3600,
    }
    tenant = db.scalar(select(Tenant).limit(1))
    r = client.get(
        f"/api/v1/integrations/oauth/callback?key=microsoft_teams&code=ac&state=microsoft_teams:{tenant.id}"
    )
    assert r.status_code == 200, r.text
    row = db.scalar(
        select(TenantIntegration).where(TenantIntegration.key == "microsoft_teams")
    )
    assert row is not None
    assert row.access_token_encrypted.startswith("v")
    assert row.refresh_token_encrypted.startswith("v")


def test_event_handling_posts_to_graph(client, auth_headers, fake_http, db):
    """A crm.deal.won event with team_id+channel_id configured should
    POST to the Graph channel-messages endpoint with the bearer token."""
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    _FakeHttp.responses[token_url] = {"access_token": "ms-graph-token", "expires_in": 3600}
    tenant = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=microsoft_teams&code=ac&state=microsoft_teams:{tenant.id}"
    )
    # Configure team + channel on the row
    row = db.scalar(
        select(TenantIntegration).where(TenantIntegration.key == "microsoft_teams")
    )
    row.config = dict(row.config or {})
    row.config["team_id"] = "TEAM-1"
    row.config["channel_id"] = "CHAN-1"
    db.commit()
    _FakeHttp.instances.clear()

    publish_event(
        "crm.deal.won",
        payload={"name": "Acme Corp", "amount": 50000},
        tenant_id=tenant.id,
    )
    posts = [p for inst in _FakeHttp.instances for p in inst.posts]
    msg_posts = [p for p in posts if "/teams/TEAM-1/channels/CHAN-1/messages" in p["url"]]
    assert len(msg_posts) == 1
    body = json.loads(msg_posts[0]["content"].decode())
    assert "Acme Corp" in body["body"]["content"]
    assert msg_posts[0]["headers"]["Authorization"] == "Bearer ms-graph-token"


def test_uninstall_clears_row(client, auth_headers, fake_http, db):
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    _FakeHttp.responses[token_url] = {"access_token": "tok", "expires_in": 3600}
    tenant = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=microsoft_teams&code=ac&state=microsoft_teams:{tenant.id}"
    )
    r = client.post("/api/v1/integrations/microsoft_teams/uninstall", headers=auth_headers)
    assert r.status_code == 204
    db.expire_all()
    assert db.scalar(
        select(TenantIntegration).where(TenantIntegration.key == "microsoft_teams")
    ) is None


def test_cross_tenant_isolation(client, auth_headers, fake_http, db, make_tenant):
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    _FakeHttp.responses[token_url] = {"access_token": "tok-A", "expires_in": 3600}
    tenant_a = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=microsoft_teams&code=ac&state=microsoft_teams:{tenant_a.id}"
    )

    _tenant_b, _user_b, token_b = make_tenant("msteams-iso-b")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    r = client.get("/api/v1/integrations/installed", headers=headers_b)
    assert r.status_code == 200
    keys = [row["key"] for row in r.json()]
    assert "microsoft_teams" not in keys
