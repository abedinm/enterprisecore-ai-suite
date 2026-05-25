"""ETag helper: stable hashing + 304 short-circuit."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.etag import compute_etag, etag_response


def _row(id: str, updated_at: str):
    return SimpleNamespace(id=id, updated_at=updated_at)


def test_compute_etag_stable_for_same_rows():
    rows = [_row("a", "2026-01-01T00:00:00Z"), _row("b", "2026-01-02T00:00:00Z")]
    a = compute_etag(rows)
    b = compute_etag(rows)
    assert a == b


def test_compute_etag_changes_when_row_updates():
    a = compute_etag([_row("a", "2026-01-01T00:00:00Z")])
    b = compute_etag([_row("a", "2026-01-01T00:00:01Z")])
    assert a != b


def test_compute_etag_order_sensitive():
    a = compute_etag([_row("a", "2026-01-01"), _row("b", "2026-01-02")])
    b = compute_etag([_row("b", "2026-01-02"), _row("a", "2026-01-01")])
    assert a != b


@pytest.fixture()
def etag_app() -> TestClient:
    app = FastAPI()

    @app.get("/things")
    def things(request: Request):
        rows = [_row("a", "2026-01-01")]
        return etag_response(request, rows)

    return TestClient(app)


def test_etag_response_emits_header_and_body(etag_app):
    r = etag_app.get("/things")
    assert r.status_code == 200
    et = r.headers.get("etag")
    assert et and et.startswith('"')


def test_etag_short_circuits_on_match(etag_app):
    r1 = etag_app.get("/things")
    et = r1.headers["etag"]
    r2 = etag_app.get("/things", headers={"If-None-Match": et})
    assert r2.status_code == 304
    assert r2.headers["etag"] == et


def test_etag_no_match_re_serialises(etag_app):
    r = etag_app.get("/things", headers={"If-None-Match": '"different"'})
    assert r.status_code == 200
    assert r.headers["etag"] != '"different"'
