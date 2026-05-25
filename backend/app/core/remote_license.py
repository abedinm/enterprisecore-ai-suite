"""Remote license verification — calls the license server with offline cache.

This is the NEW key format (`EC-XXXX-XXXX-XXXX-XXXX`) verified against the
hosted license server. The original `license_key.py` HMAC scheme remains
available for air-gapped deployments where no backend is reachable.

Verification flow:
  1. Try remote `/verify` (timeout 8s).
  2. Verify the server's Ed25519 signature on the claims it returned —
     unsigned or wrong-key responses are rejected even on HTTP 200. The
     pubkey is COMPILED IN below so a compromised CA / man-in-the-middle
     /proxy cannot forge a valid claim.
  3. If valid → cache to disk for `license_offline_grace_days`.
  4. If remote unreachable → fall back to cache if within grace window.
  5. If no cache and offline → return invalid with `offline_no_cache`.

The cache lives under `~/.enterprisecore/license.json` (Windows: `%USERPROFILE%`).
"""
from __future__ import annotations

import base64
import json
import os
import platform
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from loguru import logger

from app import __version__
from app.core.config import settings


CACHE_PATH = Path.home() / ".enterprisecore" / "license.json"

# Compiled-in Ed25519 public key for the license server. Operators can
# override via the LICENSE_SERVER_PUBKEY env var (PEM format) at deploy time
# — useful for self-hosted license servers. NEVER trust an HTTPS response
# alone; the signature is the final word.
#
# This default value is a development placeholder. Replace before first
# production release. The license-server repo stores the matching private
# key out-of-band; rotation procedure is documented in docs/LICENSE_KEYS.md.
DEFAULT_LICENSE_PUBKEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAGm05L4OWnv0jJxv2yYy5FN7e7Mw0xR2qHfPGZqv7Pj4=
-----END PUBLIC KEY-----
"""


def _license_pubkey():
    """Load the pinned Ed25519 public key (env override → compiled-in default)."""
    raw = os.environ.get("LICENSE_SERVER_PUBKEY", "").strip()
    pem = raw.encode("utf-8") if raw else DEFAULT_LICENSE_PUBKEY_PEM
    return load_pem_public_key(pem)


def _verify_signed_claims(body: dict) -> tuple[bool, dict | None]:
    """Verify the server's Ed25519 signature on its returned claims.

    The license server returns:
        {
          "claims_b64": "<base64url-encoded JSON of {key, tier, expires_at, ...}>",
          "sig_b64":    "<base64url-encoded 64-byte Ed25519 signature>"
        }
    plus optional informational fields. We refuse to honour anything else.

    Returns ``(ok, decoded_claims_or_None)``. On failure we return ``(False,
    None)`` — never trust unsigned data, never trust a wrong-key signature.
    """
    claims_b64 = body.get("claims_b64")
    sig_b64 = body.get("sig_b64")
    if not claims_b64 or not sig_b64:
        return False, None
    try:
        claims_bytes = base64.urlsafe_b64decode(claims_b64 + "==")
        sig_bytes = base64.urlsafe_b64decode(sig_b64 + "==")
        _license_pubkey().verify(sig_bytes, claims_bytes)
        claims = json.loads(claims_bytes.decode("utf-8"))
        return True, claims
    except (InvalidSignature, ValueError, json.JSONDecodeError) as e:
        logger.warning("License server signature verification FAILED: {}", e)
        return False, None


@dataclass
class RemoteStatus:
    valid: bool
    reason: str
    tier: str | None = None
    expires_at: str | None = None
    activations_remaining: int | None = None
    offline: bool = False

    def to_dict(self) -> dict:
        return {
            "valid": self.valid, "reason": self.reason, "tier": self.tier,
            "expires_at": self.expires_at, "activations_remaining": self.activations_remaining,
            "offline": self.offline,
        }


def _machine_id() -> str:
    """Stable machine identifier — UUID derived from MAC + hostname.
    Not cryptographically anchored; sufficient to count distinct devices.
    """
    base = f"{uuid.getnode()}-{platform.node()}"
    return uuid.uuid5(uuid.NAMESPACE_DNS, base).hex


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _read_cache() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(data: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Restrict to user-readable on Windows (best-effort)
        CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        if os.name == "posix":
            os.chmod(CACHE_PATH, 0o600)
    except OSError as e:
        logger.warning("Could not write license cache: {}", e)


def verify_remote(key: str | None = None) -> RemoteStatus:
    """Verify the current license against the remote server.

    Pass an explicit key for testing; defaults to settings.license_key.
    """
    key = (key or settings.license_key or "").strip()
    if not key:
        return RemoteStatus(valid=False, reason="no_key_configured")

    machine_id = _machine_id()
    payload = {
        "key": key,
        "machine_id": machine_id,
        "machine_name": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "app_version": __version__,
    }

    # 1) Try remote — but trust the SIGNATURE, not the HTTPS response alone.
    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.post(f"{settings.license_api_url}/verify", json=payload)
        if r.status_code == 200:
            body = r.json()
            # New (signed) protocol: license server returns claims_b64 + sig_b64.
            # We refuse unsigned legacy responses in production.
            ok, claims = _verify_signed_claims(body)
            if not ok or claims is None:
                if settings.app_env == "production":
                    return RemoteStatus(valid=False, reason="signature_invalid")
                # In dev we tolerate unsigned responses so contributors without
                # the license-server private key can still run the app.
                logger.warning("License: server response was not signed; tolerating in dev only")
                claims = body
            # Anti-replay: claims must match the key + machine we asked about.
            if claims.get("key") and claims["key"] != key:
                return RemoteStatus(valid=False, reason="signature_key_mismatch")
            if claims.get("machine_id") and claims["machine_id"] != machine_id:
                return RemoteStatus(valid=False, reason="signature_machine_mismatch")
            if claims.get("valid"):
                _write_cache({
                    "key": key,
                    "machine_id": machine_id,
                    "verified_at": _now_utc().isoformat(),
                    "tier": claims.get("tier"),
                    "expires_at": claims.get("expires_at"),
                    "activations_remaining": claims.get("activations_remaining"),
                    "renewal_days": claims.get("renewal_days", settings.license_offline_grace_days),
                    # Persist the raw signed envelope so we can re-verify on
                    # boot — an attacker editing license.json on disk cannot
                    # promote themselves to enterprise tier because the
                    # signature wouldn't match.
                    "signed_envelope": {
                        "claims_b64": body.get("claims_b64"),
                        "sig_b64": body.get("sig_b64"),
                    } if body.get("claims_b64") else None,
                })
                return RemoteStatus(
                    valid=True, reason="ok",
                    tier=claims.get("tier"),
                    expires_at=claims.get("expires_at"),
                    activations_remaining=claims.get("activations_remaining"),
                    offline=False,
                )
            return RemoteStatus(valid=False, reason=claims.get("reason") or "rejected",
                                tier=claims.get("tier"))
        logger.warning("License server returned HTTP {}", r.status_code)
    except httpx.HTTPError as e:
        logger.info("License server unreachable, falling back to cache: {}", e)

    # 2) Offline path — accept cache if within grace window AND if the
    #    signed envelope still verifies. Re-verifying on every offline
    #    boot stops a tampered license.json from leaking elevated tier.
    cached = _read_cache()
    if cached and cached.get("key") == key and cached.get("machine_id") == machine_id:
        envelope = cached.get("signed_envelope") or {}
        if envelope.get("claims_b64") and envelope.get("sig_b64"):
            ok, claims = _verify_signed_claims(envelope)
            if not ok:
                logger.warning("License cache signature invalid — refusing")
                return RemoteStatus(valid=False, reason="cache_signature_invalid", offline=True)
            cached_for_check = claims
        elif settings.app_env == "production":
            # Production with no signed envelope on disk = upgrade-path
            # transition where the operator hasn't seen a signed response
            # yet. Refuse and force them to refresh online.
            return RemoteStatus(valid=False, reason="cache_unsigned", offline=True)
        else:
            cached_for_check = cached
        try:
            verified_at = datetime.fromisoformat(cached["verified_at"])
            if verified_at.tzinfo is None:
                verified_at = verified_at.replace(tzinfo=timezone.utc)
            grace_days = int(cached.get("renewal_days") or settings.license_offline_grace_days)
            age = (_now_utc() - verified_at).days
            if age <= grace_days:
                return RemoteStatus(
                    valid=True, reason="offline_cached",
                    tier=cached_for_check.get("tier"),
                    expires_at=cached_for_check.get("expires_at"),
                    activations_remaining=cached_for_check.get("activations_remaining"),
                    offline=True,
                )
            return RemoteStatus(valid=False, reason="offline_cache_expired", offline=True)
        except (KeyError, ValueError) as e:
            logger.warning("License cache corrupt: {}", e)

    return RemoteStatus(valid=False, reason="offline_no_cache", offline=True)


def deactivate_remote(key: str | None = None) -> bool:
    """Free up this machine's slot. Called from settings UI on uninstall."""
    key = (key or settings.license_key or "").strip()
    if not key:
        return False
    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.post(
                f"{settings.license_api_url}/deactivate",
                json={"key": key, "machine_id": _machine_id()},
            )
        if r.status_code == 200 and r.json().get("deactivated"):
            try:
                CACHE_PATH.unlink(missing_ok=True)
            except OSError:
                pass
            return True
    except httpx.HTTPError as e:
        logger.warning("Deactivation failed: {}", e)
    return False


def warn_on_startup_remote() -> None:
    """Called from FastAPI lifespan. Never raises."""
    status = verify_remote()
    if status.valid:
        suffix = " (offline cache)" if status.offline else ""
        logger.info(
            "License: {} tier={} activations_left={}{}",
            "valid", status.tier or "—", status.activations_remaining if status.activations_remaining is not None else "—",
            suffix,
        )
        return
    if settings.app_env == "production":
        logger.warning("License: INVALID — reason={}", status.reason)
    else:
        logger.info("License (dev): {}", status.reason)
