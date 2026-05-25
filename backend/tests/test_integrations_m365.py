"""Microsoft 365 (Calendar + Mail + SharePoint) integration tests."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter
from app.models.integrations import TenantIntegration
from app.models.tenant import Tenant
from app.services.event_bus import publish_event, reset_subscribers
from app.services.integrations import register_all_subscribers
from app.services.integrations import microsoft_365 as m365_mod


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
    m365_mod.set_http_client_factory(lambda: _FakeHttp())
    yield _FakeHttp
    m365_mod.set_http_client_factory(None)


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


def test_install_url_lists_m365_scopes(client, auth_headers):
    r = client.post("/api/v1/integrations/microsoft_365/install", headers=auth_headers)
    assert r.status_code == 200, r.text
    url = r.json()["install_url"]
    assert url.startswith("https://login.microsoftonline.com/")
    assert "Calendars.ReadWrite" in url
    assert "Mail.Send" in url
    assert "Files.ReadWrite" in url


def test_callback_persists_token(client, auth_headers, fake_http, db):
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    _FakeHttp.responses[token_url] = {
        "access_token": "m365-token",
        "refresh_token": "m365-refresh",
        "expires_in": 3600,
    }
    tenant = db.scalar(select(Tenant).limit(1))
    r = client.get(
        f"/api/v1/integrations/oauth/callback?key=microsoft_365&code=ac&state=microsoft_365:{tenant.id}"
    )
    assert r.status_code == 200, r.text
    row = db.scalar(
        select(TenantIntegration).where(TenantIntegration.key == "microsoft_365")
    )
    assert row is not None
    assert row.config["default_calendar_id"] == "primary"
    assert row.config["sync_calendar_enabled"] is True


def test_project_created_posts_calendar_event(client, auth_headers, fake_http, db):
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    _FakeHttp.responses[token_url] = {"access_token": "m365-token", "expires_in": 3600}
    tenant = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=microsoft_365&code=ac&state=microsoft_365:{tenant.id}"
    )
    _FakeHttp.instances.clear()

    publish_event(
        "projects.project.created",
        payload={
            "title": "Kickoff",
            "kickoff_at": "2026-06-01T10:00:00+00:00",
            "description": "Phase 1",
        },
        tenant_id=tenant.id,
    )
    posts = [p for inst in _FakeHttp.instances for p in inst.posts]
    cal_posts = [p for p in posts if p["url"].endswith("/me/events")]
    assert len(cal_posts) == 1
    body = json.loads(cal_posts[0]["content"].decode())
    assert body["subject"] == "Kickoff"
    assert body["start"]["timeZone"] == "UTC"
    assert cal_posts[0]["headers"]["Authorization"] == "Bearer m365-token"


def test_sharepoint_upload_skipped_when_unset(client, auth_headers, fake_http, db):
    """marketing.upload events must not crash when sharepoint_site_id is
    None — they should log + skip."""
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    _FakeHttp.responses[token_url] = {"access_token": "tok", "expires_in": 3600}
    tenant = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=microsoft_365&code=ac&state=microsoft_365:{tenant.id}"
    )
    _FakeHttp.instances.clear()

    publish_event(
        "marketing.upload",
        payload={"filename": "asset.png", "content_base64": "aGVsbG8="},
        tenant_id=tenant.id,
    )
    posts = [p for inst in _FakeHttp.instances for p in inst.posts]
    sp_posts = [p for p in posts if "/sites/" in p["url"]]
    assert len(sp_posts) == 0  # silently skipped


def test_uninstall_clears_row(client, auth_headers, fake_http, db):
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    _FakeHttp.responses[token_url] = {"access_token": "tok", "expires_in": 3600}
    tenant = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=microsoft_365&code=ac&state=microsoft_365:{tenant.id}"
    )
    r = client.post("/api/v1/integrations/microsoft_365/uninstall", headers=auth_headers)
    assert r.status_code == 204
    db.expire_all()
    assert db.scalar(
        select(TenantIntegration).where(TenantIntegration.key == "microsoft_365")
    ) is None
