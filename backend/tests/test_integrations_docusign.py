"""DocuSign integration tests."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter
from app.models.integrations import TenantIntegration
from app.models.tenant import Tenant
from app.services.event_bus import publish_event, reset_subscribers, subscribe
from app.services.integrations import register_all_subscribers
from app.services.integrations import docusign as ds_mod


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
    ds_mod.set_http_client_factory(lambda: _FakeHttp())
    yield _FakeHttp
    ds_mod.set_http_client_factory(None)


@pytest.fixture(autouse=True)
def _wipe(monkeypatch):
    monkeypatch.setenv("DOCUSIGN_CLIENT_ID", "ds-test-id")
    monkeypatch.setenv("DOCUSIGN_CLIENT_SECRET", "ds-test-secret")
    monkeypatch.setenv("DOCUSIGN_BASE_URL", "https://account-d.docusign.com")
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


def test_install_url_uses_docusign_auth(client, auth_headers):
    r = client.post("/api/v1/integrations/docusign/install", headers=auth_headers)
    assert r.status_code == 200, r.text
    url = r.json()["install_url"]
    assert url.startswith("https://account-d.docusign.com/oauth/auth")
    assert "client_id=ds-test-id" in url
    assert "scope=signature" in url


def test_callback_persists_account_id(client, auth_headers, fake_http, db):
    _FakeHttp.responses["https://account-d.docusign.com/oauth/token"] = {
        "access_token": "ds-token",
        "refresh_token": "ds-refresh",
        "account_id": "ACC-123",
        "base_uri": "https://demo.docusign.net",
    }
    tenant = db.scalar(select(Tenant).limit(1))
    r = client.get(
        f"/api/v1/integrations/oauth/callback?key=docusign&code=ac&state=docusign:{tenant.id}"
    )
    assert r.status_code == 200, r.text
    row = db.scalar(select(TenantIntegration).where(TenantIntegration.key == "docusign"))
    assert row is not None
    assert row.access_token_encrypted.startswith("v")
    assert row.config["account_id"] == "ACC-123"
    assert row.config["auto_send"] is True


def test_event_creates_envelope(client, auth_headers, fake_http, db):
    """A crm.proposal.sent event should POST an envelope to DocuSign."""
    _FakeHttp.responses["https://account-d.docusign.com/oauth/token"] = {
        "access_token": "ds-token",
        "account_id": "ACC-1",
        "base_uri": "https://demo.docusign.net",
    }
    tenant = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=docusign&code=ac&state=docusign:{tenant.id}"
    )
    _FakeHttp.instances.clear()

    publish_event(
        "crm.proposal.sent",
        payload={
            "title": "Acme Proposal",
            "document_id": "doc-99",
            "recipient_email": "buyer@acme.test",
            "recipient_name": "Buyer Smith",
        },
        tenant_id=tenant.id,
    )
    posts = [p for inst in _FakeHttp.instances for p in inst.posts]
    env_posts = [p for p in posts if "/restapi/v2.1/accounts/ACC-1/envelopes" in p["url"]]
    assert len(env_posts) == 1
    body = json.loads(env_posts[0]["content"].decode())
    assert body["status"] == "sent"
    assert body["recipients"]["signers"][0]["email"] == "buyer@acme.test"
    assert env_posts[0]["headers"]["Authorization"] == "Bearer ds-token"


def test_inbound_completed_fires_event(client, auth_headers, fake_http, db):
    """The DocuSign Connect inbound webhook should publish
    ``docusign.envelope.completed`` when the envelope is signed."""
    _FakeHttp.responses["https://account-d.docusign.com/oauth/token"] = {
        "access_token": "tok", "account_id": "ACC-1", "base_uri": "https://demo.docusign.net",
    }
    tenant = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=docusign&code=ac&state=docusign:{tenant.id}"
    )

    captured: list = []

    def _capture(ev):
        captured.append(ev)

    subscribe("docusign.envelope.completed", _capture)

    r = client.post(
        f"/api/v1/integrations/docusign/inbound?tenant_id={tenant.id}",
        json={
            "envelopeId": "env-77",
            "status": "completed",
            "customFields": {
                "textCustomFields": [
                    {"name": "ec_document_id", "value": "doc-42"},
                ]
            },
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"
    assert any(e.type == "docusign.envelope.completed" for e in captured)


def test_uninstall_clears_row(client, auth_headers, fake_http, db):
    _FakeHttp.responses["https://account-d.docusign.com/oauth/token"] = {
        "access_token": "tok", "account_id": "ACC-1",
    }
    tenant = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=docusign&code=ac&state=docusign:{tenant.id}"
    )
    r = client.post("/api/v1/integrations/docusign/uninstall", headers=auth_headers)
    assert r.status_code == 204
    db.expire_all()
    assert db.scalar(select(TenantIntegration).where(TenantIntegration.key == "docusign")) is None


def test_cross_tenant_isolation(client, auth_headers, fake_http, db, make_tenant):
    _FakeHttp.responses["https://account-d.docusign.com/oauth/token"] = {
        "access_token": "tok-A", "account_id": "ACC-A",
    }
    tenant_a = db.scalar(select(Tenant).limit(1))
    client.get(
        f"/api/v1/integrations/oauth/callback?key=docusign&code=ac&state=docusign:{tenant_a.id}"
    )

    _tenant_b, _user_b, token_b = make_tenant("docusign-iso-b")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    r = client.get("/api/v1/integrations/installed", headers=headers_b)
    assert r.status_code == 200
    keys = [row["key"] for row in r.json()]
    assert "docusign" not in keys
