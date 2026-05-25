"""Public /status JSON + /status.html sanity tests."""
from __future__ import annotations


def test_status_json_shape(client):
    r = client.get("/status/")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") in ("ok", "degraded", "down")
    probes = body.get("probes") or {}
    assert "app" in probes and "database" in probes
    assert probes["app"]["status"] == "ok"
    assert probes["database"]["status"] in ("ok", "degraded", "down")


def test_status_html_renders(client):
    r = client.get("/status/html")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "System Status" in r.text
    assert "ok" in r.text or "degraded" in r.text or "down" in r.text


def test_status_no_auth_required(client):
    """External monitors hit this without a token; must not 401."""
    r = client.get("/status/", headers={"Authorization": "Bearer not-a-real-token"})
    # Either we accept anonymous (200) or we accept the wrong token but
    # treat the route as anonymous (200). What we must NOT see is 401.
    assert r.status_code == 200
