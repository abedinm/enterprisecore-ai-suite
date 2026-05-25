"""Response-cache decorator tests.

Covers:
* MISS → HIT inside the TTL window (DB roundtrip count drops on the
  second call).
* TTL expiry forces a re-fill.
* Cross-tenant isolation — tenant A's cache entry doesn't leak to
  tenant B even though both hit the same URL.
* Mutation-driven invalidation — creating a custom role drops the
  cached ``/rbac/permissions`` response for the same tenant.
"""
from __future__ import annotations

import time

import pytest

from app.core import cache as cache_mod
from app.services.query_perf import count_queries


@pytest.fixture(autouse=True)
def _fresh_cache():
    """Each test starts with an empty cache so previous tests' hits
    don't poison the MISS/HIT assertions here."""
    cache_mod.set_backend(cache_mod._MemoryBackend())
    yield
    cache_mod.set_backend(cache_mod._MemoryBackend())


def test_cache_hit_records_hit_in_stats(client, auth_headers):
    """Second identical GET returns from cache → backend records a HIT.

    The /modules endpoint serves an in-memory catalog, so we can't
    reliably measure query-count drop; instead we assert via the cache's
    own hit/miss counters that the second call really came from cache.
    """
    cache_mod.set_backend(cache_mod._MemoryBackend())

    r1 = client.get("/api/v1/modules", headers=auth_headers)
    assert r1.status_code == 200
    after_first = cache_mod.stats()
    assert after_first["misses"] >= 1
    assert after_first["hits"] == 0

    r2 = client.get("/api/v1/modules", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json() == r1.json()

    after_second = cache_mod.stats()
    assert after_second["hits"] >= 1, after_second
    assert after_second["misses"] == after_first["misses"]


def test_cache_hit_rate_metric(client, auth_headers):
    """A single MISS + several HITs should land hit-rate above 0.5."""
    # Reset stats by re-seeding the backend so previous tests don't bias.
    cache_mod.set_backend(cache_mod._MemoryBackend())
    for _ in range(5):
        resp = client.get("/api/v1/modules", headers=auth_headers)
        assert resp.status_code == 200
    stats = cache_mod.stats()
    assert stats["hits"] >= 4
    assert stats["misses"] >= 1
    assert stats["hit_rate"] > 0.5


def test_ttl_expiry_forces_refill():
    """Past the TTL, get() reports a miss and the value must be re-set."""
    backend = cache_mod._MemoryBackend()
    backend.set("k", {"v": 1}, ttl=0.05)
    assert backend.get("k") == {"v": 1}
    time.sleep(0.1)
    assert backend.get("k") is None


def test_cross_tenant_isolation(client, make_tenant):
    """Two tenants hitting the same URL get two separate cache entries."""
    _, _, token_a = make_tenant("perf-cache-a")
    _, _, token_b = make_tenant("perf-cache-b")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    cache_mod.set_backend(cache_mod._MemoryBackend())

    r1 = client.get("/api/v1/modules", headers=headers_a)
    r2 = client.get("/api/v1/modules", headers=headers_b)
    assert r1.status_code == 200
    assert r2.status_code == 200

    # Both calls should have produced separate misses — keys are namespaced
    # by tenant, so tenant B's first call cannot have been served by
    # tenant A's cached entry.
    stats = cache_mod.stats()
    assert stats["misses"] >= 2


def test_mutation_invalidates_cache(client, auth_headers):
    """Creating a custom role busts the cached /rbac/permissions entry."""
    cache_mod.set_backend(cache_mod._MemoryBackend())

    # Prime the cache.
    r1 = client.get("/api/v1/rbac/permissions", headers=auth_headers)
    assert r1.status_code == 200
    primed = cache_mod.stats()["hits"]

    # Hit it again — confirm we're actually serving from cache now.
    r2 = client.get("/api/v1/rbac/permissions", headers=auth_headers)
    assert r2.status_code == 200
    assert cache_mod.stats()["hits"] == primed + 1

    # Mutate via the role-create endpoint, which calls
    # invalidate_for_tenant("rbac:permissions") on success.
    create_resp = client.post(
        "/api/v1/rbac/roles",
        headers=auth_headers,
        json={
            "name": "cache-bust-role",
            "description": "perf test",
            "permission_keys": [],
        },
    )
    assert create_resp.status_code in (200, 201), create_resp.text

    # Next call should be a MISS (the invalidation wiped the entry).
    miss_before = cache_mod.stats()["misses"]
    r3 = client.get("/api/v1/rbac/permissions", headers=auth_headers)
    assert r3.status_code == 200
    assert cache_mod.stats()["misses"] == miss_before + 1


def test_invalidate_prefix_returns_count():
    backend = cache_mod._MemoryBackend()
    backend.set("rbac:permissions:t=A:1", [1], ttl=60)
    backend.set("rbac:permissions:t=A:2", [2], ttl=60)
    backend.set("rbac:permissions:t=B:1", [3], ttl=60)
    cache_mod.set_backend(backend)

    deleted = cache_mod.invalidate("rbac:permissions:t=A:")
    assert deleted == 2
    # Tenant B's entry is intact.
    assert backend.get("rbac:permissions:t=B:1") == [3]
