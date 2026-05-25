"""Backend translation lookup.

A deliberately small, file-based catalog. At import time every JSON file in
``app/locales/`` is loaded into memory; ``translate(key, locale, **kwargs)``
returns the matching string with optional ``{placeholder}`` interpolation
and falls back to English (then to the key itself) when a translation is
missing.

The companion ``get_request_locale(request)`` FastAPI dependency picks the
best supported language from the ``Accept-Language`` header, with a fallback
chain of: explicit header → authenticated user's ``locale`` → tenant
default → ``en``. It is intentionally cheap (no DB hit unless the chain
walks past the header).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import Request

# ---------------------------------------------------------------------------
# Supported locales — must match the frontend's SUPPORTED_LOCALES.
# ---------------------------------------------------------------------------
SUPPORTED_LOCALES: tuple[str, ...] = (
    "en", "es", "fr", "de", "pt", "it", "ja", "zh", "ar", "he", "ur",
)
DEFAULT_LOCALE = "en"

# Locales requiring right-to-left layout. Surfaced via API for clients.
RTL_LOCALES: frozenset[str] = frozenset({"ar", "he", "ur"})

_LOCALES_DIR = Path(__file__).resolve().parents[1] / "locales"


def _load_catalogs() -> dict[str, dict[str, str]]:
    """Load every ``app/locales/<code>.json`` into memory once.

    Missing files are treated as empty catalogs so partial roll-outs don't
    crash startup. Logged-but-tolerated to keep the app boot fast.
    """
    out: dict[str, dict[str, str]] = {}
    for code in SUPPORTED_LOCALES:
        path = _LOCALES_DIR / f"{code}.json"
        if path.exists():
            try:
                out[code] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                out[code] = {}
        else:
            out[code] = {}
    return out


# Lazy single-load — wraps in lru_cache so tests can call ``_load_catalogs.cache_clear()``
# after fixture mutation if they ever need a fresh read.
@lru_cache(maxsize=1)
def _catalogs() -> dict[str, dict[str, str]]:
    return _load_catalogs()


def _lookup(key: str, locale: str) -> str | None:
    """Return the raw string for ``key`` in ``locale`` (None if missing)."""
    return _catalogs().get(locale, {}).get(key)


def translate(key: str, locale: str | None = None, /, **kwargs: Any) -> str:
    """Return ``key`` translated into ``locale``.

    Falls back to English; if even English is missing the key itself is
    returned so logs and clients still get something readable. ``**kwargs``
    are interpolated with ``str.format_map`` so ``{name}`` placeholders work.
    """
    code = _normalize(locale) if locale else DEFAULT_LOCALE
    text = _lookup(key, code) or _lookup(key, DEFAULT_LOCALE) or key
    if kwargs:
        try:
            text = text.format_map(_SafeDict(kwargs))
        except Exception:
            # Bad placeholder shouldn't crash the request — fall through to
            # the un-interpolated string.
            pass
    return text


class _SafeDict(dict):
    """Format-map dict that leaves unknown placeholders intact."""

    def __missing__(self, k: str) -> str:  # noqa: D401
        return "{" + k + "}"


# ---------------------------------------------------------------------------
# Accept-Language parsing
# ---------------------------------------------------------------------------
_LANG_RE = re.compile(r"\s*([A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*)\s*(?:;\s*q=([0-9.]+))?")


def _normalize(code: str) -> str:
    """Reduce ``zh-CN`` → ``zh`` and lower-case the result.

    Region/script subtags are dropped — the catalogs are keyed by primary
    language only. Unknown languages collapse to the default locale.
    """
    if not code:
        return DEFAULT_LOCALE
    primary = code.split("-", 1)[0].lower()
    return primary if primary in SUPPORTED_LOCALES else DEFAULT_LOCALE


def parse_accept_language(header: str | None) -> str:
    """Return the best supported locale from an ``Accept-Language`` header.

    Examples:
        ``"fr-FR,fr;q=0.9,en;q=0.7"`` → ``"fr"``
        ``"zh-CN;q=0.8"``             → ``"zh"``
        ``"xx-YY"``                   → ``"en"`` (falls back to default)
        ``None`` / ``""``             → ``"en"``
    """
    if not header:
        return DEFAULT_LOCALE
    best: tuple[float, str] | None = None
    for tag, q in _LANG_RE.findall(header):
        if not tag:
            continue
        weight = float(q) if q else 1.0
        primary = tag.split("-", 1)[0].lower()
        if primary in SUPPORTED_LOCALES:
            if best is None or weight > best[0]:
                best = (weight, primary)
    return best[1] if best else DEFAULT_LOCALE


def get_request_locale(request: Request) -> str:
    """FastAPI dep: best supported locale for the current request.

    Order of preference:
        1. ``Accept-Language`` header (parsed for quality factors).
        2. Authenticated user's ``locale`` (set on ``request.state.user`` by
           an earlier middleware / dependency, when available).
        3. Tenant default locale (``request.state.tenant.locale``).
        4. ``DEFAULT_LOCALE`` (``en``).

    Step 1 wins if the header lists *any* supported locale; this keeps
    public/anonymous endpoints honest about the visitor's preferred
    language. Steps 2–4 only kick in when the header is empty or
    unrecognised.
    """
    header_pick = parse_accept_language(request.headers.get("accept-language"))
    if header_pick != DEFAULT_LOCALE:
        return header_pick

    # Best-effort fallbacks — these attributes may not be present for
    # anonymous requests; getattr keeps the dep crash-free.
    user = getattr(request.state, "user", None)
    if user is not None:
        user_locale = getattr(user, "locale", None)
        if user_locale:
            return _normalize(user_locale)

    tenant = getattr(request.state, "tenant", None)
    if tenant is not None:
        tenant_locale = getattr(tenant, "locale", None) or getattr(tenant, "default_locale", None)
        if tenant_locale:
            return _normalize(tenant_locale)

    return DEFAULT_LOCALE


__all__ = [
    "DEFAULT_LOCALE",
    "RTL_LOCALES",
    "SUPPORTED_LOCALES",
    "get_request_locale",
    "parse_accept_language",
    "translate",
]
