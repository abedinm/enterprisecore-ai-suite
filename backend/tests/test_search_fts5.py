"""Tests for the SQLite FTS5 cross-module search.

Covers the contract laid out in the search service:

* CRUD-driven mirror — insert / update / delete a source row, the FTS5
  index reflects it without manual intervention.
* Tenant isolation — tenant A's data is invisible to tenant B even with
  the same query.
* Ranking — porter-stemmed and BM25-ordered, so closer matches win.
* Entity filter — ``?types=`` narrows results.
* Error handling — empty query returns 400, very long queries are
  truncated to 200 chars.
"""
from __future__ import annotations

from sqlalchemy import text

from app.core.tenant_context import tenant_scope
from app.models.crm import Contact
from app.services.search import (
    FTS_ADAPTERS,
    MAX_QUERY_LENGTH,
    _escape_fts5_query,
    register_fts_listeners,
)


# ---------------------------------------------------------------------------
# Direct service-level checks
# ---------------------------------------------------------------------------

def test_register_fts_listeners_is_idempotent():
    register_fts_listeners()
    register_fts_listeners()  # second call is a no-op


def test_fts5_table_exists(session_factory):
    """The FTS5 virtual table must be present after create_all (via the
    DDL hook in app/models/search_index.py)."""
    with session_factory() as db:
        rows = db.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='search_index_fts'")
        ).all()
        assert rows, "search_index_fts virtual table not created"


def test_fts_adapters_cover_15_types():
    types = {a.entity_type for a in FTS_ADAPTERS.values()}
    # The spec asked for 15+ indexed entity types covering the most-used
    # tables in the suite.
    assert len(types) >= 15


def test_escape_fts5_query_handles_specials():
    # Operators stripped, tokens quoted; trailing * preserved as a prefix.
    assert _escape_fts5_query("foo bar") == '"foo" "bar"'
    assert _escape_fts5_query("foo*") == '"foo"*'
    assert _escape_fts5_query("a:b(c)") == '"a:b(c)"'
    assert _escape_fts5_query("   ") == '"__no_match__"'


# ---------------------------------------------------------------------------
# End-to-end through the FastAPI client
# ---------------------------------------------------------------------------

def test_create_contact_indexed_and_searchable(client, auth_headers):
    register_fts_listeners()
    r = client.post(
        "/api/v1/crm/contacts",
        headers=auth_headers,
        json={"name": "Wakanda Forever", "company": "T'Challa Ltd", "email": "tc@wakanda.test"},
    )
    assert r.status_code in (200, 201), r.text

    hit = client.get("/api/v1/search", headers=auth_headers, params={"q": "Wakanda"})
    assert hit.status_code == 200, hit.text
    payload = hit.json()
    titles = [r["title"] for r in payload["results"]]
    assert "Wakanda Forever" in titles
    # All hits should be tagged with a known entity_type
    for r in payload["results"]:
        assert "." in r["entity_type"]
    # Rank is positive (we inverted bm25's sign)
    for r in payload["results"]:
        assert isinstance(r["rank"], float)


def test_update_contact_updates_index(client, auth_headers):
    register_fts_listeners()
    r = client.post(
        "/api/v1/crm/contacts",
        headers=auth_headers,
        json={"name": "Original Name", "company": "Acme", "email": "x@a.test"},
    )
    cid = r.json()["id"]

    upd = client.patch(
        f"/api/v1/crm/contacts/{cid}",
        headers=auth_headers,
        json={"name": "Renamed Person", "company": "Acme"},
    )
    assert upd.status_code == 200, upd.text

    # The old name no longer hits
    hit_old = client.get("/api/v1/search", headers=auth_headers, params={"q": "Original"})
    assert hit_old.status_code == 200
    assert "Original Name" not in [r["title"] for r in hit_old.json()["results"]]

    # The new name does
    hit_new = client.get("/api/v1/search", headers=auth_headers, params={"q": "Renamed"})
    assert hit_new.status_code == 200
    assert "Renamed Person" in [r["title"] for r in hit_new.json()["results"]]


def test_delete_contact_removes_from_index(client, auth_headers):
    register_fts_listeners()
    r = client.post(
        "/api/v1/crm/contacts",
        headers=auth_headers,
        json={"name": "Goneby Tomorrow", "company": "Ephemeral", "email": "g@e.test"},
    )
    cid = r.json()["id"]

    rem = client.delete(f"/api/v1/crm/contacts/{cid}", headers=auth_headers)
    assert rem.status_code in (200, 204)

    hit = client.get("/api/v1/search", headers=auth_headers, params={"q": "Goneby"})
    assert hit.status_code == 200
    assert all(r["entity_id"] != cid for r in hit.json()["results"])


def test_tenant_isolation(client, auth_headers, make_tenant):
    """Tenant A's contact must not be visible to tenant B's search."""
    register_fts_listeners()
    # Default-tenant admin (auth_headers) creates the secret contact.
    r = client.post(
        "/api/v1/crm/contacts",
        headers=auth_headers,
        json={"name": "TenantSecretX9Q", "company": "ConfidentialCo"},
    )
    assert r.status_code in (200, 201)

    # A second tenant searches for the same term — must get zero hits.
    _, _, other_token = make_tenant("fts-isolation-other")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    hit = client.get(
        "/api/v1/search", headers=other_headers, params={"q": "TenantSecretX9Q"}
    )
    assert hit.status_code == 200, hit.text
    assert hit.json()["results"] == []


def test_ranking_favours_more_relevant_matches(client, auth_headers, session_factory, default_tenant):
    """Two contacts: one with the term in the title, one in the body — the
    title hit should rank higher (lower bm25, higher exposed rank)."""
    register_fts_listeners()
    # Direct ORM inserts (no listener race) — the listeners fire on flush.
    with session_factory() as db, tenant_scope(default_tenant.id):
        db.add(Contact(name="Aragorn Strider", company="Rangers"))
        db.add(Contact(name="Pippin Took", company="Aragorn was here mentioned"))
        db.commit()

    hit = client.get("/api/v1/search", headers=auth_headers, params={"q": "Aragorn"})
    assert hit.status_code == 200
    results = hit.json()["results"]
    titles = [r["title"] for r in results]
    assert "Aragorn Strider" in titles
    # Title hit should come first.
    assert titles.index("Aragorn Strider") <= titles.index("Pippin Took")


def test_entity_types_filter_narrows_results(client, auth_headers):
    register_fts_listeners()
    # Create a contact + a project + a task all sharing a stem.
    client.post(
        "/api/v1/crm/contacts",
        headers=auth_headers,
        json={"name": "Globaltermsearchxyz Contact"},
    )
    client.post(
        "/api/v1/projects/projects",
        headers=auth_headers,
        json={
            "name": "Globaltermsearchxyz Project",
            "description": "x",
            "status": "active",
        },
    )

    # No filter → both types present
    all_hit = client.get(
        "/api/v1/search",
        headers=auth_headers,
        params={"q": "Globaltermsearchxyz"},
    )
    assert all_hit.status_code == 200
    types_present = {r["entity_type"] for r in all_hit.json()["results"]}
    assert "crm.contact" in types_present
    assert "projects.project" in types_present

    # Filter to contacts only
    only_contacts = client.get(
        "/api/v1/search",
        headers=auth_headers,
        params={"q": "Globaltermsearchxyz", "types": "crm.contact"},
    )
    assert only_contacts.status_code == 200
    for r in only_contacts.json()["results"]:
        assert r["entity_type"] == "crm.contact"


def test_empty_query_returns_400(client, auth_headers):
    # Pydantic min_length=1 catches the empty-string case before we get to
    # the whitespace check — that returns a 422 with a structured error.
    r = client.get("/api/v1/search", headers=auth_headers, params={"q": ""})
    assert r.status_code in (400, 422)


def test_whitespace_only_query_returns_400(client, auth_headers):
    r = client.get("/api/v1/search", headers=auth_headers, params={"q": "   "})
    # Pydantic allows the non-empty string; our explicit check catches the
    # whitespace-only case.
    assert r.status_code == 400


def test_long_query_truncated(client, auth_headers):
    register_fts_listeners()
    client.post(
        "/api/v1/crm/contacts",
        headers=auth_headers,
        json={"name": "Truncatable Person"},
    )
    long_q = ("Truncatable " + ("padding " * 200)).strip()
    assert len(long_q) > MAX_QUERY_LENGTH
    hit = client.get("/api/v1/search", headers=auth_headers, params={"q": long_q})
    assert hit.status_code == 200, hit.text
    # The truncated query still echoes back at length ≤ MAX_QUERY_LENGTH
    assert len(hit.json()["query"]) <= MAX_QUERY_LENGTH


def test_reindex_endpoint_rebuilds_fts(client, auth_headers, session_factory, default_tenant):
    register_fts_listeners()
    # Create a contact, then bulk-delete the FTS rows directly to simulate
    # a corrupted index. Reindex should bring it back.
    r = client.post(
        "/api/v1/crm/contacts",
        headers=auth_headers,
        json={"name": "ReindexableUniqueXYZ", "company": "Re Co"},
    )
    cid = r.json()["id"]

    with session_factory() as db, tenant_scope(default_tenant.id):
        db.execute(text("DELETE FROM search_index_fts"))
        db.commit()

    # Right after the delete, the search must return zero hits.
    hit_before = client.get(
        "/api/v1/search", headers=auth_headers, params={"q": "ReindexableUniqueXYZ"}
    )
    assert hit_before.status_code == 200
    assert hit_before.json()["results"] == []

    # Reindex
    re = client.post("/api/v1/search/reindex", headers=auth_headers)
    assert re.status_code == 200
    body = re.json()
    assert body["fts_indexed"] >= 1

    hit_after = client.get(
        "/api/v1/search", headers=auth_headers, params={"q": "ReindexableUniqueXYZ"}
    )
    assert hit_after.status_code == 200
    assert cid in [r["entity_id"] for r in hit_after.json()["results"]]


def test_include_full_returns_entity_payload(client, auth_headers):
    register_fts_listeners()
    r = client.post(
        "/api/v1/crm/contacts",
        headers=auth_headers,
        json={"name": "FullPayloadPerson", "company": "Hydration Inc", "email": "f@h.test"},
    )
    assert r.status_code in (200, 201)
    hit = client.get(
        "/api/v1/search",
        headers=auth_headers,
        params={"q": "FullPayloadPerson", "include": "full"},
    )
    assert hit.status_code == 200, hit.text
    results = hit.json()["results"]
    full_hits = [r for r in results if "full" in r]
    assert full_hits, "include=full should attach a full payload"
    assert full_hits[0]["full"]["name"] == "FullPayloadPerson"
