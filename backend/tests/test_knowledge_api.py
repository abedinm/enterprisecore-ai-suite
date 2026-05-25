"""Knowledge Hub API tests — KB CRUD, document basic flow, ingestion is
covered separately in test_knowledge_ingest.py with mocked parsers/embedders."""
from __future__ import annotations

import pytest


def _create_kb(client, auth_headers, **overrides):
    body = {
        "name": "Engineering Wiki",
        "description": "Internal eng docs",
        "embedding_provider": "ollama",
        "embedding_model": "nomic-embed-text",
        "embedding_dim": 768,
        "chunk_size": 800,
        "chunk_overlap": 100,
        **overrides,
    }
    r = client.post("/api/v1/knowledge/kb", headers=auth_headers, json=body)
    return r


def test_create_kb_minimal(client, auth_headers):
    r = _create_kb(client, auth_headers)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["name"] == "Engineering Wiki"
    assert data["embedding_dim"] == 768
    assert data["document_count"] == 0
    assert data["chunk_count"] == 0
    assert data["is_active"] is True


def test_create_kb_rejects_invalid_overlap(client, auth_headers):
    r = _create_kb(client, auth_headers, chunk_size=400, chunk_overlap=500)
    assert r.status_code == 422
    assert "overlap" in r.text.lower()


def test_list_kbs(client, auth_headers):
    _create_kb(client, auth_headers, name="KB A")
    _create_kb(client, auth_headers, name="KB B")
    r = client.get("/api/v1/knowledge/kb", headers=auth_headers)
    assert r.status_code == 200
    items = r.json()
    names = [k["name"] for k in items]
    assert "KB A" in names and "KB B" in names


def test_get_kb_includes_counts(client, auth_headers):
    kb = _create_kb(client, auth_headers, name="Counts Check").json()
    r = client.get(f"/api/v1/knowledge/kb/{kb['id']}", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["document_count"] == 0
    assert data["chunk_count"] == 0
    assert data["ready_count"] == 0


def test_patch_kb(client, auth_headers):
    kb = _create_kb(client, auth_headers, name="Editable").json()
    r = client.patch(
        f"/api/v1/knowledge/kb/{kb['id']}",
        headers=auth_headers,
        json={"description": "Updated desc", "chunk_size": 1200},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["description"] == "Updated desc"
    assert data["chunk_size"] == 1200


def test_patch_kb_overlap_validation(client, auth_headers):
    kb = _create_kb(client, auth_headers, name="OverlapCheck").json()
    r = client.patch(
        f"/api/v1/knowledge/kb/{kb['id']}",
        headers=auth_headers,
        json={"chunk_size": 200, "chunk_overlap": 300},
    )
    assert r.status_code == 422


def test_delete_kb(client, auth_headers):
    kb = _create_kb(client, auth_headers, name="Delete Me").json()
    r = client.delete(f"/api/v1/knowledge/kb/{kb['id']}", headers=auth_headers)
    assert r.status_code == 204
    r2 = client.get(f"/api/v1/knowledge/kb/{kb['id']}", headers=auth_headers)
    assert r2.status_code == 404


def test_get_missing_kb(client, auth_headers):
    r = client.get("/api/v1/knowledge/kb/nonexistent", headers=auth_headers)
    assert r.status_code == 404


def test_kb_endpoints_require_auth(client):
    # Clear any cookies left over from prior tests' login (TestClient persists
    # the access_token cookie across the session-scoped client fixture).
    client.cookies.clear()
    r = client.get("/api/v1/knowledge/kb")
    assert r.status_code == 401


def test_documents_empty_list(client, auth_headers):
    kb = _create_kb(client, auth_headers, name="Empty Docs").json()
    r = client.get(f"/api/v1/knowledge/kb/{kb['id']}/documents", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_list_queries_empty(client, auth_headers):
    r = client.get("/api/v1/knowledge/queries", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
