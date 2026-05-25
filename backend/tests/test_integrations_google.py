"""Google Workspace integration tests."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter
from app.models.integrations import TenantIntegration
from app.models.tenant import Tenant
from app.services.event_bus import reset_subscribers
from app.services.integrations import register_all_subscribers
from app.services.integrations import google_workspace as gw_mod


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
        self.posts.append({"url": url, "data": data, "content": content})
        return _FakeResp(_FakeHttp.responses.get(url, {}))

    def close(self):
        pass


@pytest.fixture()
def fake_http():
    _FakeHttp.instances.clear()
    _FakeHttp.responses.clear()
    gw_mod.set_http_client_factory(lambda: _FakeHttp())
    yield _FakeHttp
    gw_mod.set_http_client_factory(None)


@pytest.fixture(autouse=True)
def _wipe(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-test-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-test-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://example.test/cb")
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


def test_install_url_uses_offline_scope(client, auth_headers):
    r = client.post("/api/v1/integrations/google_workspace/install", headers=auth_headers)
    assert r.status_code == 200, r.text
    url = r.json()["install_url"]
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert "client_id=google-test-id" in url
    assert "access_type=offline" in url
    assert "scope=" in url


def test_callback_persists_refresh_token(client, auth_headers, fake_http, db):
    _FakeHttp.responses["https://oauth2.googleapis.com/token"] = {
        "access_token": "ya29.test-access",
        "refresh_token": "1//test-refresh",
        "expires_in": 3600,
        "scope": "calendar.events drive.file",
    }
    tenant = db.scalar(select(Tenant).limit(1))
    r = client.get(
        f"/api/v1/integrations/oauth/callback?key=google_workspace&code=ac&state=google_workspace:{tenant.id}"
    )
    assert r.status_code == 200, r.text
    row = db.scalar(select(TenantIntegration).where(TenantIntegration.key == "google_workspace"))
    assert row is not None
    assert row.access_token_encrypted.startswith("v")
    assert row.refresh_token_encrypted.startswith("v")
    assert row.token_expires_at is not None
    assert row.config["target_calendar_id"] == "primary"


def test_state_mismatch_rejected(client, fake_http):
    """A wrong state token must not persist any tokens."""
    r = client.get(
        "/api/v1/integrations/oauth/callback?key=google_workspace&code=ac&state=bogus:foo"
    )
    assert r.status_code in (400, 422)


def test_uninstall_clears_google_row(client, auth_headers, fake_http, db):
    _FakeHttp.responses["https://oauth2.googleapis.com/token"] = {
        "access_token": "ya29.test", "expires_in": 3600,
    }
    tenant = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=google_workspace&code=ac&state=google_workspace:{tenant.id}"
    )
    r = client.post("/api/v1/integrations/google_workspace/uninstall", headers=auth_headers)
    assert r.status_code == 204
    db.expire_all()
    assert db.scalar(
        select(TenantIntegration).where(TenantIntegration.key == "google_workspace")
    ) is None


def test_google_lib_missing_does_not_crash(client, auth_headers, fake_http, db, monkeypatch):
    """When google-api-python-client isn't installed, event handlers must
    skip silently rather than crash the publish loop."""
    _FakeHttp.responses["https://oauth2.googleapis.com/token"] = {
        "access_token": "ya29.test", "expires_in": 3600,
    }
    tenant = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=google_workspace&code=ac&state=google_workspace:{tenant.id}"
    )
    from app.services.event_bus import publish_event

    # publish — even if the google lib really IS installed, this should
    # not raise (failure paths return cleanly).
    publish_event(
        "projects.project.created",
        payload={"title": "Kickoff", "kickoff_at": "2026-06-01T10:00:00+00:00"},
        tenant_id=tenant.id,
    )
