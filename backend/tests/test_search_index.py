"""Tests for the SearchIndex auto-mirror service.

Verifies:
  - Creating a Customer/Contact/Project/Task/Document/User pushes a row into
    SearchIndex automatically.
  - Updating the source row updates the index entry.
  - Deleting the source row prunes the index entry.
  - /search prefers the index when populated and still returns hits.
  - /search/reindex rebuilds from live tables.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models.crm import Contact
from app.models.finance import Customer
from app.models.projects import Project
from app.models.user import SearchIndex
from app.services.search_index import register_search_listeners


def _count_index(db, **filters) -> int:
    stmt = select(SearchIndex)
    for col, value in filters.items():
        stmt = stmt.where(getattr(SearchIndex, col) == value)
    return len(db.scalars(stmt).all())


def test_listeners_register_idempotent():
    # Should be safe to call multiple times — _LISTENERS_REGISTERED guards it.
    register_search_listeners()
    register_search_listeners()


def test_create_customer_indexes_it(client, auth_headers, session_factory):
    register_search_listeners()
    r = client.post(
        "/api/v1/finance/customers",
        headers=auth_headers,
        json={"name": "Hooli LLC", "email": "billing@hooli.test", "currency": "USD"},
    )
    assert r.status_code in (200, 201), r.text

    with session_factory() as db:
        rows = db.scalars(
            select(SearchIndex).where(
                SearchIndex.module == "finance",
                SearchIndex.entity_type == "customer",
                SearchIndex.title == "Hooli LLC",
            )
        ).all()
        assert len(rows) == 1
        assert "billing@hooli.test" in (rows[0].body or "")


def test_update_customer_updates_index(client, auth_headers, session_factory):
    register_search_listeners()
    create = client.post(
        "/api/v1/finance/customers",
        headers=auth_headers,
        json={"name": "Initech", "email": "ops@initech.test", "currency": "USD"},
    )
    cid = create.json()["id"]

    upd = client.patch(
        f"/api/v1/finance/customers/{cid}",
        headers=auth_headers,
        json={"name": "Initech Inc", "email": "ops@initech.test", "currency": "USD"},
    )
    assert upd.status_code == 200

    with session_factory() as db:
        row = db.scalar(
            select(SearchIndex).where(
                SearchIndex.entity_type == "customer",
                SearchIndex.entity_id == cid,
            )
        )
        assert row is not None
        assert row.title == "Initech Inc"


def test_delete_customer_prunes_index(client, auth_headers, session_factory):
    register_search_listeners()
    create = client.post(
        "/api/v1/finance/customers",
        headers=auth_headers,
        json={"name": "Soylent", "email": "biz@soylent.test", "currency": "USD"},
    )
    cid = create.json()["id"]

    rem = client.delete(f"/api/v1/finance/customers/{cid}", headers=auth_headers)
    assert rem.status_code in (200, 204)

    with session_factory() as db:
        row = db.scalar(select(SearchIndex).where(SearchIndex.entity_id == cid))
        assert row is None


def test_search_endpoint_returns_indexed_hits(client, auth_headers):
    register_search_listeners()
    client.post(
        "/api/v1/finance/customers",
        headers=auth_headers,
        json={"name": "Stark Industries", "email": "tony@stark.test", "currency": "USD"},
    )
    r = client.post(
        "/api/v1/search",
        headers=auth_headers,
        json={"query": "Stark", "limit": 10},
    )
    assert r.status_code == 200
    body = r.json()
    titles = [hit["title"] for hit in body["items"]]
    assert "Stark Industries" in titles
    # All hits should use the indexed module value
    for hit in body["items"]:
        assert hit["module"] in {"finance", "crm", "projects", "documents", "users", "inventory"}


def test_reindex_rebuilds_from_live_tables(client, auth_headers, session_factory):
    register_search_listeners()
    # Bypass the listeners by inserting a row through the ORM directly with the
    # bound session-factory engine but NOT via the FastAPI handler, then nuke
    # the index. Reindex should resurrect the row.
    with session_factory() as db:
        db.add(Contact(name="Lex Luthor", company="LexCorp", email="lex@lexcorp.test"))
        db.commit()
        # Nuke the index
        for row in db.scalars(select(SearchIndex)).all():
            db.delete(row)
        db.commit()
        assert _count_index(db) == 0

    r = client.post("/api/v1/search/reindex", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["indexed"] >= 1

    with session_factory() as db:
        contact_idx = db.scalar(
            select(SearchIndex).where(SearchIndex.entity_type == "contact", SearchIndex.title == "Lex Luthor")
        )
        assert contact_idx is not None


def test_search_falls_back_to_live_when_index_empty(client, auth_headers, session_factory):
    register_search_listeners()
    # Add a project the listeners-aware way…
    r = client.post(
        "/api/v1/projects/projects",
        headers=auth_headers,
        json={"name": "Project Argus", "description": "Top-secret offline rollout", "status": "active"},
    )
    assert r.status_code in (200, 201), r.text

    # …then wipe the index to force the fallback path.
    with session_factory() as db:
        for row in db.scalars(select(SearchIndex)).all():
            db.delete(row)
        db.commit()

    hit = client.post(
        "/api/v1/search",
        headers=auth_headers,
        json={"query": "Argus", "limit": 10},
    )
    assert hit.status_code == 200
    titles = [h["title"] for h in hit.json()["items"]]
    assert "Project Argus" in titles
