"""In-process response cache for safe GET endpoints.

Design goals
------------
* **Tenant-safe.** The cache key always folds in the current tenant id from
  ``tenant_context``. Two tenants asking ``GET /modules`` get two cache
  entries — never one shared one.
* **Drop-in.** A function-level decorator that wraps any FastAPI endpoint
  handler. The wrapped handler keeps its FastAPI dependency signature, so
  ``Depends(...)`` for auth/db keeps working unchanged.
* **TTL-based.** Each entry has an expiry timestamp. Lookups past the
  expiry behave like a miss and re-execute the handler.
* **Optional Redis.** If ``REDIS_URL`` is set in ``settings``, the cache
  delegates to Redis; otherwise it falls back to a process-local
  ``OrderedDict`` with a soft size cap. The Redis path is intentionally
  best-effort — any Redis error degrades to in-process.
* **Explicit invalidation.** ``invalidate(prefix)`` lets mutating endpoints
  wipe everything that starts with a given key prefix (e.g. all
  ``rbac:permissions:`` entries for the current tenant after a custom-role
  change).

What we *don't* cache
---------------------
Per-user state (notifications, jobs, recent activity), per-tenant business
data (invoices, customers, deals), and anything that depends on a query
parameter we can't deterministically fold into the key. The decorator
honors a ``vary_by`` allowlist so any other variation source must be
declared explicitly.
"""
from __future__ import annotations

import functools
import hashlib
import json
import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Callable

from fastapi import Response

from app.core.config import settings
from app.core.tenant_context import get_current_tenant_id


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------
class _MemoryBackend:
    """Bounded LRU dict + per-key TTL. Thread-safe via a single lock — the
    cache is for read-mostly traffic, so contention is negligible compared
    to skipping a DB roundtrip."""

    def __init__(self, max_entries: int = 2048) -> None:
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = Lock()
        self._max = max_entries
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            expires_at, value = entry
            if expires_at < time.monotonic():
                # Expired — drop and report a miss so the caller re-fills.
                self._store.pop(key, None)
                self._misses += 1
                return None
            # LRU touch
            self._store.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl: float) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + ttl, value)
            self._store.move_to_end(key)
            while len(self._store) > self._max:
                self._store.popitem(last=False)

    def invalidate(self, prefix: str) -> int:
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                self._store.pop(k, None)
            return len(keys)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            rate = (self._hits / total) if total else 0.0
            return {
                "backend": "memory",
                "size": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(rate, 4),
            }


class _RedisBackend:
    """Thin Redis wrapper. Falls back to ``_MemoryBackend`` if the import
    or initial PING fails — the memory backend is created lazily so we
    don't double-allocate when Redis is healthy."""

    def __init__(self, url: str) -> None:
        import redis  # type: ignore

        self._client = redis.Redis.from_url(url, decode_responses=False)
        # PING up front — a 5-line endpoint shouldn't spend two RTTs
        # discovering Redis is dead.
        self._client.ping()
        self._fallback: _MemoryBackend | None = None
        self._hits = 0
        self._misses = 0

    def _fb(self) -> _MemoryBackend:
        if self._fallback is None:
            self._fallback = _MemoryBackend()
        return self._fallback

    def get(self, key: str) -> Any | None:
        try:
            raw = self._client.get(key)
        except Exception:
            return self._fb().get(key)
        if raw is None:
            self._misses += 1
            return None
        try:
            self._hits += 1
            return json.loads(raw)
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: float) -> None:
        try:
            self._client.set(key, json.dumps(value, default=str), ex=int(ttl))
        except Exception:
            self._fb().set(key, value, ttl)

    def invalidate(self, prefix: str) -> int:
        # SCAN+DEL — bounded so a huge namespace doesn't block the event loop.
        deleted = 0
        try:
            cursor = 0
            while True:
                cursor, keys = self._client.scan(cursor=cursor, match=f"{prefix}*", count=200)
                if keys:
                    self._client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
        except Exception:
            deleted += self._fb().invalidate(prefix)
        return deleted

    def clear(self) -> None:
        try:
            self._client.flushdb()
        except Exception:
            pass
        if self._fallback is not None:
            self._fallback.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> dict:
        total = self._hits + self._misses
        rate = (self._hits / total) if total else 0.0
        out = {
            "backend": "redis",
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(rate, 4),
        }
        if self._fallback is not None:
            out["fallback"] = self._fallback.stats()
        return out


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------
_backend: _MemoryBackend | _RedisBackend | None = None


def _get_backend() -> _MemoryBackend | _RedisBackend:
    """Lazy-init the singleton backend.

    Tests can swap it via ``set_backend(_MemoryBackend())`` if they need
    a deterministic state.
    """
    global _backend
    if _backend is not None:
        return _backend
    redis_url = getattr(settings, "redis_url", None)
    if redis_url:
        try:
            _backend = _RedisBackend(redis_url)
            return _backend
        except Exception:
            pass
    _backend = _MemoryBackend()
    return _backend


def set_backend(backend: _MemoryBackend | _RedisBackend) -> None:
    """Override the cache backend — test-only escape hatch."""
    global _backend
    _backend = backend


def reset() -> None:
    """Wipe the cache. Primarily for tests."""
    _get_backend().clear()


def stats() -> dict:
    return _get_backend().stats()


def invalidate(prefix: str) -> int:
    """Drop every entry whose key starts with ``prefix``. Returns the count
    deleted so callers can log the impact of a mutation."""
    return _get_backend().invalidate(prefix)


def invalidate_for_tenant(namespace: str, tenant_id: str | None = None) -> int:
    """Wipe every cached entry for a (namespace, tenant) pair.

    The cache key shape is ``{namespace}:t={tenant}:...``; if no tenant is
    provided we use the current request's tenant context.
    """
    tid = tenant_id if tenant_id is not None else get_current_tenant_id() or "_"
    return invalidate(f"{namespace}:t={tid}:")


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------
def _hash_inputs(parts: dict) -> str:
    """Stable short digest of a dict (sorted keys) for the cache-key tail."""
    if not parts:
        return ""
    blob = json.dumps(parts, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _make_key(namespace: str, tenant_id: str | None, key_tail: str) -> str:
    return f"{namespace}:t={tenant_id or '_'}:{key_tail}"


def cache_response(
    *,
    ttl: int,
    namespace: str,
    vary_by: tuple[str, ...] | list[str] = (),
    include_user: bool = False,
) -> Callable:
    """Decorator that caches a FastAPI endpoint's JSON response.

    Args:
        ttl: Cache time-to-live in seconds.
        namespace: Stable prefix for invalidation. Choose one per logical
            cache group (e.g. ``"rbac:permissions"``).
        vary_by: Names of kwargs to fold into the key. Use this for query
            params that change the response shape (``status``, ``limit``).
            **Do not** list user/tenant identifiers here — tenant is
            always folded; user is folded only when ``include_user=True``.
        include_user: Set when the response depends on the calling user
            (e.g. ``/license/features`` resolves the user's plan).

    The decorated handler is still a normal FastAPI handler — it keeps its
    parameter names and ``Depends`` signature, so OpenAPI generation,
    request validation, and DI all work unchanged.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tenant_id = get_current_tenant_id()
            parts: dict[str, Any] = {}
            for name in vary_by:
                if name in kwargs:
                    parts[name] = kwargs[name]
            if include_user:
                # Standard kwarg names used across the codebase. Either may
                # be present depending on the endpoint signature.
                user = kwargs.get("current_user") or kwargs.get("current")
                if user is not None:
                    parts["user"] = getattr(user, "id", None)

            key = _make_key(namespace, tenant_id, _hash_inputs(parts))
            backend = _get_backend()

            cached = backend.get(key)
            if cached is not None:
                # Re-emit cache headers + a marker so tests can confirm a hit.
                response = kwargs.get("response")
                if isinstance(response, Response):
                    response.headers["Cache-Control"] = f"private, max-age={ttl}"
                    response.headers["X-Cache"] = "HIT"
                return cached

            value = func(*args, **kwargs)
            # JSONable payloads only — Pydantic models go through model_dump
            # so the cached value survives a process restart unchanged.
            stored = value
            if hasattr(value, "model_dump"):
                stored = value.model_dump(mode="json")
            elif isinstance(value, list) and value and hasattr(value[0], "model_dump"):
                stored = [v.model_dump(mode="json") for v in value]
            backend.set(key, stored, ttl)

            response = kwargs.get("response")
            if isinstance(response, Response):
                response.headers["Cache-Control"] = f"private, max-age={ttl}"
                response.headers["X-Cache"] = "MISS"
            return value

        wrapper.__cache_namespace__ = namespace  # type: ignore[attr-defined]
        wrapper.__cache_ttl__ = ttl  # type: ignore[attr-defined]
        return wrapper

    return decorator
