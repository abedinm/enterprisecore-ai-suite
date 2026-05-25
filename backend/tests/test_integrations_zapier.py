"""Zapier integration tests."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter
from app.models.integrations import TenantIntegration
from app.services.event_bus import publish_event, reset_subscribers
from app.services.integrations import register_all_subscribers
from app.services.integrations import zapier as zap_mod


class _FakeResp:
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self._data = data or {}
        self.text = ""

    def json(self):
        return self._data


class _FakeHttp:
    instances: list = []

    def __init__(self):
        self.posts: list[dict] = []
        _FakeHttp.instances.append(self)

    def post(self, url, content=None, headers=None, timeout=None):
        self.posts.append({
            "url": url, "content": content, "headers": dict(headers or {}),
        })
        return _FakeResp()

    def close(self):
        pass


@pytest.fixture()
def fake_http():
    _FakeHttp.instances.clear()
    zap_mod.set_http_client_factory(lambda: _FakeHttp())
    yield _FakeHttp
    zap_mod.set_http_client_factory(None)


@pytest.fixture(autouse=True)
def _wipe():
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


def test_install_returns_api_key(client, auth_headers):
    r = client.post("/api/v1/integrations/zapier/install", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["requires_oauth"] is False
    assert body["api_key"].startswith("zk_")
    assert body["install_url"] is None


def test_outbound_webhook_posts_on_event(client, auth_headers, fake_http, db):
    r = client.post("/api/v1/integrations/zapier/install", headers=auth_headers)
    api_key = r.json()["api_key"]

    # Configure the outbound URL via the config endpoint.
    client.patch(
        "/api/v1/integrations/zapier/config",
        headers=auth_headers,
        json={"config": {"outbound_webhook_url": "https://hooks.zapier.test/123"}},
    )
    from app.models.tenant import Tenant
    tenant = db.scalar(select(Tenant).limit(1))
    publish_event("crm.lead.created", payload={"name": "Lead1"}, tenant_id=tenant.id)

    posts = [p for inst in _FakeHttp.instances for p in inst.posts]
    matching = [p for p in posts if p["url"] == "https://hooks.zapier.test/123"]
    assert len(matching) == 1
    body = json.loads(matching[0]["content"].decode())
    assert body["type"] == "crm.lead.created"
    assert body["payload"]["name"] == "Lead1"


def test_inbound_creates_lead_with_valid_key(client, auth_headers, fake_http, db):
    r = client.post("/api/v1/integrations/zapier/install", headers=auth_headers)
    api_key = r.json()["api_key"]

    r = client.post(
        f"/api/v1/integrations/zapier/inbound?key={api_key}",
        json={"action": "create_crm_lead", "data": {
            "name": "Inbound Lead", "email": "lead@test.com",
            "company": "TestCo", "source": "zapier-test",
        }},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert "lead_id" in body

    from app.models.crm import Lead
    leads = db.scalars(select(Lead)).all()
    assert any(l.id == body["lead_id"] for l in leads)


def test_inbound_rejects_bad_key(client, auth_headers, fake_http):
    # Install one tenant's key so the lookup table isn't empty
    client.post("/api/v1/integrations/zapier/install", headers=auth_headers)
    r = client.post(
        "/api/v1/integrations/zapier/inbound?key=zk_bogus_never_issued",
        json={"action": "create_crm_lead", "data": {"name": "x"}},
    )
    assert r.status_code == 401
