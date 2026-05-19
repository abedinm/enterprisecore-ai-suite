"""End-to-end test: bursting /auth/login from one IP eventually gets 429s."""
from __future__ import annotations

from app.core.rate_limit import reset_dependency_limiter


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
