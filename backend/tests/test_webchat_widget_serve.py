"""Static serve for the embeddable web-chat widget at /widget.js.

These tests cover only the static handler in app.main; they don't depend on
the (future) /api/v1/webchat/* routers.
"""
from __future__ import annotations


def test_widget_get_returns_200(client):
    r = client.get("/widget.js")
    assert r.status_code == 200, r.text


def test_widget_content_type_is_javascript(client):
    r = client.get("/widget.js")
    ct = r.headers.get("content-type", "")
    assert ct.startswith("application/javascript"), ct


def test_widget_has_permissive_cors_header(client):
    r = client.get("/widget.js")
    assert r.headers.get("access-control-allow-origin") == "*"


def test_widget_has_cache_control_header(client):
    r = client.get("/widget.js")
    cc = r.headers.get("cache-control", "")
    assert "max-age" in cc, cc


def test_widget_body_contains_init_attribute(client):
    """The embed contract: the widget must read `data-bot-id` from its <script> tag."""
    r = client.get("/widget.js")
    assert "data-bot-id" in r.text


def test_widget_body_references_chat_endpoint(client):
    """The widget must POST to the EnterpriseCore web-chat path, not LinguaBot's."""
    r = client.get("/widget.js")
    assert "/api/v1/webchat/chat/" in r.text


def test_widget_head_works(client):
    """FileResponse should auto-handle HEAD via Starlette's request router."""
    r = client.head("/widget.js")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/javascript")
