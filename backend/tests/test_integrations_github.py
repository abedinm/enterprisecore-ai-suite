"""GitHub integration tests."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter
from app.models.integrations import TenantIntegration
from app.models.tenant import Tenant
from app.services.event_bus import publish_event, reset_subscribers, subscribe
from app.services.integrations import register_all_subscribers
from app.services.integrations import github as gh_mod


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
        self.gets: list[dict] = []
        _FakeHttp.instances.append(self)

    def post(self, url, content=None, data=None, headers=None, timeout=None):
        self.posts.append({
            "url": url, "content": content, "data": data,
            "headers": dict(headers or {}),
        })
        return _FakeResp(_FakeHttp.responses.get(url, {}))

    def get(self, url, headers=None, timeout=None):
        self.gets.append({"url": url, "headers": dict(headers or {})})
        return _FakeResp(_FakeHttp.responses.get(url, {}))

    def close(self):
        pass


@pytest.fixture()
def fake_http():
    _FakeHttp.instances.clear()
    _FakeHttp.responses.clear()
    gh_mod.set_http_client_factory(lambda: _FakeHttp())
    yield _FakeHttp
    gh_mod.set_http_client_factory(None)


@pytest.fixture(autouse=True)
def _wipe(monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "gh-test-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "gh-test-secret")
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


def test_install_url_uses_github_authorize(client, auth_headers):
    r = client.post("/api/v1/integrations/github/install", headers=auth_headers)
    assert r.status_code == 200, r.text
    url = r.json()["install_url"]
    assert url.startswith("https://github.com/login/oauth/authorize")
    assert "client_id=gh-test-id" in url
    assert "scope=repo" in url


def test_callback_persists_token(client, auth_headers, fake_http, db):
    _FakeHttp.responses["https://github.com/login/oauth/access_token"] = {
        "access_token": "ghp-test-token",
        "scope": "repo,read:user,read:org",
    }
    tenant = db.scalar(select(Tenant).limit(1))
    r = client.get(
        f"/api/v1/integrations/oauth/callback?key=github&code=ac&state=github:{tenant.id}"
    )
    assert r.status_code == 200, r.text
    row = db.scalar(select(TenantIntegration).where(TenantIntegration.key == "github"))
    assert row is not None
    assert row.access_token_encrypted.startswith("v")
    assert row.config["connected_repos"] == []


def test_repo_connected_event_enriches_config(client, auth_headers, fake_http, db):
    """A coding.repo.connected event should call the GitHub API and store
    the repo's default branch in config."""
    _FakeHttp.responses["https://github.com/login/oauth/access_token"] = {
        "access_token": "ghp-test-token"
    }
    _FakeHttp.responses["https://api.github.com/repos/acme/widgets"] = {
        "full_name": "acme/widgets",
        "default_branch": "main",
        "clone_url": "https://github.com/acme/widgets.git",
        "private": False,
    }
    tenant = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=github&code=ac&state=github:{tenant.id}"
    )
    _FakeHttp.instances.clear()

    publish_event(
        "coding.repo.connected",
        payload={"repo": "acme/widgets"},
        tenant_id=tenant.id,
    )
    gets = [g for inst in _FakeHttp.instances for g in inst.gets]
    repo_gets = [g for g in gets if g["url"].endswith("/repos/acme/widgets")]
    assert len(repo_gets) == 1
    assert repo_gets[0]["headers"]["Authorization"] == "Bearer ghp-test-token"


def test_inbound_webhook_emits_issue_event(client, auth_headers, fake_http, db):
    """The GitHub inbound webhook should publish github.issue.opened when
    GitHub posts an issue event."""
    _FakeHttp.responses["https://github.com/login/oauth/access_token"] = {
        "access_token": "ghp-test-token"
    }
    tenant = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=github&code=ac&state=github:{tenant.id}"
    )

    captured: list = []

    def _capture(ev):
        captured.append(ev)

    subscribe("github.issue.opened", _capture)

    r = client.post(
        f"/api/v1/integrations/github/inbound?tenant_id={tenant.id}",
        json={
            "action": "opened",
            "issue": {
                "number": 12,
                "title": "Bug in widget",
                "html_url": "https://github.com/acme/widgets/issues/12",
                "assignee": {"login": "dev1"},
            },
            "repository": {"full_name": "acme/widgets"},
        },
        headers={"X-GitHub-Event": "issues"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["action"] == "opened"
    assert any(e.type == "github.issue.opened" for e in captured)


def test_uninstall_clears_row(client, auth_headers, fake_http, db):
    _FakeHttp.responses["https://github.com/login/oauth/access_token"] = {
        "access_token": "tok"
    }
    tenant = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=github&code=ac&state=github:{tenant.id}"
    )
    r = client.post("/api/v1/integrations/github/uninstall", headers=auth_headers)
    assert r.status_code == 204
    db.expire_all()
    assert db.scalar(select(TenantIntegration).where(TenantIntegration.key == "github")) is None


def test_cross_tenant_isolation(client, auth_headers, fake_http, db, make_tenant):
    _FakeHttp.responses["https://github.com/login/oauth/access_token"] = {
        "access_token": "tok-A"
    }
    tenant_a = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=github&code=ac&state=github:{tenant_a.id}"
    )

    _tenant_b, _user_b, token_b = make_tenant("github-iso-b")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    r = client.get("/api/v1/integrations/installed", headers=headers_b)
    assert r.status_code == 200
    keys = [row["key"] for row in r.json()]
    assert "github" not in keys
