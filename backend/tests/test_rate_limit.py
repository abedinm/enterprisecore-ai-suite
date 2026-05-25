"""End-to-end test: bursting /auth/login from one IP eventually gets 429s."""
from __future__ import annotations

from app.core.rate_limit import DEFAULT_WRITE_RULE, reset_dependency_limiter


def test_login_rate_limit_triggers(client):
    """The default limit is 10/minute. Burst 15 wrong-password attempts from
    the same IP; expect a mix of 401s (auth fails) and then 429s when the
    sliding window fills up."""
    reset_dependency_limiter()  # belt-and-suspenders; conftest also resets
    payload = {"email": "admin@local", "password": "wrong-password"}
    statuses = []
    for _ in range(15):
        r = client.post("/api/v1/auth/login", json=payload)
        statuses.append(r.status_code)
    # First 10 attempts should be 401 (auth failure), the rest 429 (rate limit)
    assert statuses[:10] == [401] * 10, f"first 10 should be 401, got {statuses[:10]}"
    assert all(s == 429 for s in statuses[10:]), f"after limit, expect 429, got {statuses[10:]}"
    # The 429 body should be informative
    over_limit = client.post("/api/v1/auth/login", json=payload)
    assert over_limit.status_code == 429
    body = over_limit.json()
    assert body["code"] == "rate_limited"
    assert "Retry in" in body["detail"]


def test_rate_limit_isolated_per_endpoint(client):
    """Login and register limits are tracked independently — bursting one
    shouldn't affect the other."""
    reset_dependency_limiter()
    # Fill the login bucket
    for _ in range(10):
        client.post("/api/v1/auth/login", json={"email": "x@y.z", "password": "wrong"})
    # Register should still respond (its 10/min bucket is separate)
    r = client.post("/api/v1/auth/register", json={
        "email": "burst@local.host",
        "full_name": "Burst Test",
        "password": "ThisIsAStrongPassword123!",
    })
    # Should NOT be 429 — should be 201 (created) or 409 if duplicate
    assert r.status_code in (200, 201, 409), r.text


def test_rate_limit_resets_after_reset_call(client):
    """After reset_dependency_limiter(), a previously-exhausted bucket
    should accept new requests."""
    reset_dependency_limiter()
    for _ in range(10):
        client.post("/api/v1/auth/login", json={"email": "x@y.z", "password": "w"})
    blocked = client.post("/api/v1/auth/login", json={"email": "x@y.z", "password": "w"})
    assert blocked.status_code == 429

    reset_dependency_limiter()
    after_reset = client.post("/api/v1/auth/login", json={"email": "x@y.z", "password": "w"})
    assert after_reset.status_code == 401  # auth fails, but no longer rate-limited


# ---------------------------------------------------------------------------
# Per-module write limits
# ---------------------------------------------------------------------------
# The router-level ``WriteRateLimit`` gives each business module its own
# 60/minute bucket (POST/PUT/PATCH/DELETE only). Bursting one module's writes
# from a single IP eventually returns 429 — but reads on the same module and
# writes on a different module still go through.
def _default_write_count() -> int:
    """Parse the configured 60/minute rule into an int — kept dynamic so a
    future rule change in ``DEFAULT_WRITE_RULE`` doesn't make this test stale."""
    count, _ = DEFAULT_WRITE_RULE.split("/")
    return int(count)


def test_module_write_rate_limit_blocks_burst(client, auth_headers):
    """Burst 65 finance writes — the 61st request must come back 429."""
    reset_dependency_limiter()
    limit = _default_write_count()

    statuses: list[int] = []
    for i in range(limit + 5):
        r = client.post(
            "/api/v1/finance/customers",
            headers=auth_headers,
            json={"name": f"Burst Customer {i}"},
        )
        statuses.append(r.status_code)

    allowed = sum(1 for s in statuses if s < 400)
    blocked = sum(1 for s in statuses if s == 429)
    assert allowed == limit, (
        f"first {limit} writes should pass; got allowed={allowed} statuses={statuses}"
    )
    assert blocked == 5, (
        f"writes past the limit should 429; got blocked={blocked} statuses={statuses}"
    )

    # The block payload should be the canonical rate-limit shape.
    over_limit = client.post(
        "/api/v1/finance/customers",
        headers=auth_headers,
        json={"name": "still blocked"},
    )
    assert over_limit.status_code == 429
    body = over_limit.json()
    assert body["code"] == "rate_limited"


def test_module_write_rate_limit_isolated_per_module(client, auth_headers):
    """Finance and CRM live in separate buckets — exhausting finance must
    not cap CRM."""
    reset_dependency_limiter()
    limit = _default_write_count()

    for i in range(limit):
        r = client.post(
            "/api/v1/finance/customers",
            headers=auth_headers,
            json={"name": f"Iso Customer {i}"},
        )
        assert r.status_code < 400, f"finance write {i}: {r.text}"

    # Finance is now exhausted.
    blocked = client.post(
        "/api/v1/finance/customers",
        headers=auth_headers,
        json={"name": "blocked"},
    )
    assert blocked.status_code == 429

    # CRM still has a full bucket — same access token, different module.
    crm_resp = client.post(
        "/api/v1/crm/contacts",
        headers=auth_headers,
        json={"name": "Iso CRM Contact"},
    )
    assert crm_resp.status_code != 429, crm_resp.text


def test_module_write_rate_limit_skips_get(client, auth_headers):
    """GETs are explicitly excluded from the write bucket — even after a
    write storm reads on the same module should keep returning 200."""
    reset_dependency_limiter()
    limit = _default_write_count()

    # Exhaust finance writes.
    for i in range(limit):
        r = client.post(
            "/api/v1/finance/customers",
            headers=auth_headers,
            json={"name": f"GetTest {i}"},
        )
        assert r.status_code < 400

    # Reads must still work.
    r = client.get("/api/v1/finance/customers", headers=auth_headers)
    assert r.status_code == 200, r.text


def test_module_write_rate_limit_crm_burst(client, auth_headers):
    """Smoke-check that the CRM module follows the same 60/min ceiling."""
    reset_dependency_limiter()
    limit = _default_write_count()

    for i in range(limit):
        r = client.post(
            "/api/v1/crm/contacts",
            headers=auth_headers,
            json={"name": f"CRM Burst {i}"},
        )
        assert r.status_code < 400, f"crm write {i}: {r.text}"
    blocked = client.post(
        "/api/v1/crm/contacts",
        headers=auth_headers,
        json={"name": "blocked"},
    )
    assert blocked.status_code == 429, blocked.text


def test_module_write_rate_limit_inventory_burst(client, auth_headers):
    """Smoke-check that inventory follows the same 60/min ceiling, using
    unique SKUs to avoid 409s confusing the count."""
    reset_dependency_limiter()
    limit = _default_write_count()
    statuses: list[int] = []
    for i in range(limit + 3):
        r = client.post(
            "/api/v1/inventory/products",
            headers=auth_headers,
            json={"sku": f"RL-{i:04d}", "name": f"RL Product {i}"},
        )
        statuses.append(r.status_code)
    # First ``limit`` should be non-429 (200/201/422 are all acceptable here —
    # what matters is the limiter did NOT block them); the remainder must 429.
    early_429 = [i for i, s in enumerate(statuses[:limit]) if s == 429]
    assert not early_429, f"inventory writes 429'd early at indices {early_429}"
    assert all(s == 429 for s in statuses[limit:]), (
        f"inventory writes past limit should 429; got {statuses[limit:]}"
    )
