"""OIDC SSO service.

Wraps Authlib's primitives in a thin service layer so the endpoint module
can stay focused on FastAPI plumbing. The goals:

* Hide Authlib version quirks (it's a moving target across 1.3 → 1.7).
* Cache JWKS per (tenant, issuer) for one hour so we don't hit the IdP
  on every login.
* Sign/verify the short-lived state cookie that protects /callback from
  CSRF + replay (state + nonce live there, hashed).
* Expose two preset providers — ``google`` and ``microsoft`` — as a sugar
  layer; everything else goes through the generic ``custom`` path.

The hard work — discovery, signature verification, audience checks — is
all delegated to Authlib's ``OAuth2Client`` and ``JsonWebToken`` /
``JsonWebKey`` (or joserfc when Authlib 1.5+ migrates to it).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from loguru import logger

from app.core.config import settings as app_settings


# ---------------------------------------------------------------------------
# Preset providers
# ---------------------------------------------------------------------------
PRESETS: dict[str, dict[str, Any]] = {
    "google": {
        "issuer_url": "https://accounts.google.com",
        "scopes": ["openid", "email", "profile"],
    },
    "microsoft": {
        # /common works for both personal and work accounts.
        "issuer_url": "https://login.microsoftonline.com/common/v2.0",
        "scopes": ["openid", "email", "profile"],
    },
    "okta": {
        # Customer must supply the full issuer in their config — Okta's
        # issuer is org-specific. We expose the preset for symmetry.
        "issuer_url": None,
        "scopes": ["openid", "email", "profile"],
    },
}

DEFAULT_SCOPES = ["openid", "email", "profile"]


def resolve_issuer_url(config) -> str | None:
    """Return the effective issuer URL — config wins over preset."""
    return config.issuer_url


# ---------------------------------------------------------------------------
# Discovery + JWKS caching
# ---------------------------------------------------------------------------
@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


_DISCOVERY_CACHE: dict[str, _CacheEntry] = {}
_JWKS_CACHE: dict[str, _CacheEntry] = {}
_CACHE_TTL = 3600  # 1 hour


def _cache_get(cache: dict[str, _CacheEntry], key: str) -> Any | None:
    entry = cache.get(key)
    if not entry:
        return None
    if entry.expires_at < time.time():
        cache.pop(key, None)
        return None
    return entry.value


def _cache_put(cache: dict[str, _CacheEntry], key: str, value: Any, ttl: int = _CACHE_TTL) -> None:
    cache[key] = _CacheEntry(value=value, expires_at=time.time() + ttl)


def clear_caches() -> None:
    """Wipe both discovery and JWKS caches. Used by tests + admin tooling
    when an IdP rotates its signing keys."""
    _DISCOVERY_CACHE.clear()
    _JWKS_CACHE.clear()


def fetch_discovery(issuer_url: str) -> dict[str, Any]:
    """Fetch (and cache) the OIDC discovery document. Returns the JSON
    body verbatim; callers reach into ``authorization_endpoint`` /
    ``token_endpoint`` / ``jwks_uri`` from there."""
    cached = _cache_get(_DISCOVERY_CACHE, issuer_url)
    if cached:
        return cached
    well_known = issuer_url.rstrip("/") + "/.well-known/openid-configuration"
    resp = httpx.get(well_known, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    _cache_put(_DISCOVERY_CACHE, issuer_url, data)
    return data


def fetch_jwks(jwks_uri: str) -> dict[str, Any]:
    """Fetch (and cache for 1h) the IdP's JWK set."""
    cached = _cache_get(_JWKS_CACHE, jwks_uri)
    if cached:
        return cached
    resp = httpx.get(jwks_uri, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    _cache_put(_JWKS_CACHE, jwks_uri, data)
    return data


# ---------------------------------------------------------------------------
# Signed state cookie (CSRF + nonce binding)
# ---------------------------------------------------------------------------
def _hmac(payload: bytes) -> str:
    return hmac.new(app_settings.secret_key.encode(), payload, hashlib.sha256).hexdigest()


def make_state_cookie(tenant_id: str, nonce: str, redirect_after: str | None = None) -> tuple[str, str]:
    """Mint a state string + signed cookie value.

    The state string is what we send to the IdP's /authorize endpoint as
    ``?state=...``. The cookie carries the same state PLUS the nonce and a
    HMAC so /callback can verify the IdP echoed our state and that no
    attacker spliced their own nonce in.
    """
    state = secrets.token_urlsafe(32)
    body = json.dumps(
        {
            "state": state,
            "nonce": nonce,
            "tenant_id": tenant_id,
            "redirect_after": redirect_after or "",
            "ts": int(time.time()),
        },
        separators=(",", ":"),
    ).encode()
    sig = _hmac(body)
    cookie_value = body.hex() + "." + sig
    return state, cookie_value


def verify_state_cookie(cookie_value: str, expected_state: str, max_age_seconds: int = 600) -> dict[str, Any]:
    """Decode the cookie set by ``make_state_cookie`` and verify it matches.

    Raises ``ValueError`` on tampering, expiry, or state mismatch — the
    caller turns that into a 400.
    """
    try:
        body_hex, sig = cookie_value.rsplit(".", 1)
        body = bytes.fromhex(body_hex)
    except Exception as exc:
        raise ValueError("Malformed state cookie") from exc
    if not hmac.compare_digest(sig, _hmac(body)):
        raise ValueError("State cookie signature mismatch")
    data = json.loads(body)
    if data.get("state") != expected_state:
        raise ValueError("State mismatch — possible CSRF")
    if time.time() - int(data.get("ts", 0)) > max_age_seconds:
        raise ValueError("State cookie expired")
    return data


# ---------------------------------------------------------------------------
# Token exchange + ID-token verification
# ---------------------------------------------------------------------------
def build_authorize_url(
    issuer_url: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    nonce: str,
    scopes: list[str] | None = None,
) -> str:
    """Construct the full /authorize URL we send the user's browser to.

    No need to spin up an OAuth2Client just to format query params — the
    primitives are static enough that ``urlencode`` is cleaner.
    """
    discovery = fetch_discovery(issuer_url)
    authorize_endpoint = discovery["authorization_endpoint"]
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes or DEFAULT_SCOPES),
        "state": state,
        "nonce": nonce,
    }
    return f"{authorize_endpoint}?{urlencode(params)}"


def exchange_code(
    issuer_url: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> dict[str, Any]:
    """POST the auth code to the IdP's token endpoint. Returns the raw
    token response — at minimum ``id_token``, usually ``access_token`` too.
    """
    discovery = fetch_discovery(issuer_url)
    token_endpoint = discovery["token_endpoint"]
    resp = httpx.post(
        token_endpoint,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=15,
    )
    if resp.status_code >= 400:
        logger.warning("OIDC token exchange failed: {} {}", resp.status_code, resp.text[:300])
        resp.raise_for_status()
    return resp.json()


def verify_id_token(
    id_token: str,
    issuer_url: str,
    client_id: str,
    expected_nonce: str | None = None,
) -> dict[str, Any]:
    """Verify the signed ID token against the IdP's JWKS.

    Validates:
      * Signature against the JWK identified by ``kid``
      * ``iss`` matches the configured issuer
      * ``aud`` contains our client_id
      * ``exp`` > now
      * ``nonce`` matches what we issued (when supplied)

    Returns the claims dict so the caller can map ``email`` → User.
    """
    from authlib.jose import JsonWebToken, JsonWebKey, errors as jose_errors  # type: ignore

    discovery = fetch_discovery(issuer_url)
    jwks_data = fetch_jwks(discovery["jwks_uri"])
    keys = JsonWebKey.import_key_set(jwks_data)
    jwt = JsonWebToken(["RS256", "RS384", "RS512", "ES256", "ES384", "PS256"])

    try:
        claims = jwt.decode(id_token, keys, claims_options={
            "iss": {"essential": True, "values": [issuer_url, issuer_url.rstrip("/")]},
            "aud": {"essential": True, "values": [client_id]},
            "exp": {"essential": True},
        })
        claims.validate(now=int(time.time()), leeway=30)
    except jose_errors.JoseError as exc:
        raise ValueError(f"ID token verification failed: {exc}") from exc

    if expected_nonce is not None and claims.get("nonce") != expected_nonce:
        raise ValueError("Nonce mismatch in ID token")
    return dict(claims)
