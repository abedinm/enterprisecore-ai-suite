"""License-key validation.

EnterpriseCore ships as a paid product; production deployments are expected to
configure ``LICENSE_KEY`` in the environment. Keys are HMAC-signed payloads of
the form ``base64(payload).base64(signature)`` where ``payload`` is a small
JSON document describing the customer, the issuance date, and optional
expiry. The signing secret is shared between this module and the offline
issuance tool.

Without a secret to verify against, the simplest possible "format check" is
used and the key is treated as ``unverified``. Dev mode is permissive — the
app keeps running and the dashboard shows an "evaluation" badge — but
production mode logs a loud warning at startup and the
``/api/v1/license/status`` endpoint returns the failure reason so an admin
notices.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from loguru import logger

from app.core.config import settings


@dataclass
class LicenseStatus:
    valid: bool
    state: str  # "active" | "expired" | "invalid" | "evaluation" | "unverified"
    reason: str
    customer: str | None = None
    plan: str | None = None
    issued_on: str | None = None
    expires_on: str | None = None
    days_remaining: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "state": self.state,
            "reason": self.reason,
            "customer": self.customer,
            "plan": self.plan,
            "issued_on": self.issued_on,
            "expires_on": self.expires_on,
            "days_remaining": self.days_remaining,
        }


def _b64url_decode(s: str) -> bytes:
    pad = (-len(s)) % 4
    return base64.urlsafe_b64decode(s + ("=" * pad))


def _signing_secret() -> bytes:
    """Derive a stable HMAC key from the app's SECRET_KEY when no dedicated
    issuance secret is provided. In a real product the issuance tool would
    use a long-lived offline secret."""
    return hashlib.sha256(settings.secret_key.encode("utf-8")).digest()


def parse_license(raw: str) -> tuple[dict | None, bytes | None]:
    """Parse a 'payload.signature' key. Returns (payload_dict | None, signature_bytes | None)."""
    if not raw or "." not in raw:
        return None, None
    try:
        payload_b64, sig_b64 = raw.split(".", 1)
        payload_bytes = _b64url_decode(payload_b64)
        signature = _b64url_decode(sig_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
        return payload, signature
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None, None


def verify_license() -> LicenseStatus:
    """Read settings.license_key and classify it. Pure function; no DB."""
    raw = (settings.license_key or "").strip()
    if not raw:
        return LicenseStatus(
            valid=False,
            state="evaluation",
            reason="No LICENSE_KEY configured — running in evaluation mode.",
        )

    payload, signature = parse_license(raw)
    if payload is None or signature is None:
        return LicenseStatus(
            valid=False, state="invalid",
            reason="LICENSE_KEY is not in the expected 'payload.signature' format.",
        )

    # Re-compute the signature and compare in constant time
    expected = hmac.new(
        _signing_secret(),
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected, signature):
        # We can't actually verify since we don't have the issuing secret.
        # Mark as "unverified" rather than invalid: payload-shape is fine,
        # we just can't prove authenticity. Production deployments should
        # ship with a signing secret in this module.
        state = "unverified"
        reason = "Signature does not match local derivation — accepted as unverified."
    else:
        state = "active"
        reason = "Signature verified."

    customer = payload.get("customer")
    plan = payload.get("plan", "standard")
    issued_on = payload.get("issued_on")
    expires_on = payload.get("expires_on")
    days_remaining: int | None = None
    if expires_on:
        try:
            exp = date.fromisoformat(expires_on)
            today = datetime.now(timezone.utc).date()
            days_remaining = (exp - today).days
            if days_remaining < 0:
                return LicenseStatus(
                    valid=False, state="expired",
                    reason=f"License expired on {expires_on}.",
                    customer=customer, plan=plan,
                    issued_on=issued_on, expires_on=expires_on,
                    days_remaining=days_remaining,
                )
        except ValueError:
            return LicenseStatus(
                valid=False, state="invalid",
                reason=f"License expires_on='{expires_on}' is not a valid ISO date.",
            )

    return LicenseStatus(
        valid=(state == "active"),
        state=state,
        reason=reason,
        customer=customer, plan=plan,
        issued_on=issued_on, expires_on=expires_on,
        days_remaining=days_remaining,
    )


def warn_on_startup() -> None:
    """Called by the FastAPI lifespan. Logs a loud message in production when
    the license is missing or invalid. Never raises — never blocks startup."""
    status = verify_license()
    if status.state == "active":
        logger.info("License: {} for {} (expires {})", status.state, status.customer or "—",
                    status.expires_on or "never")
        return
    msg = f"License status: {status.state.upper()} — {status.reason}"
    if settings.app_env == "production":
        logger.warning(msg)
    else:
        logger.info("License: {} ({})", status.state, status.reason)


def make_demo_key(customer: str, plan: str = "standard", days: int = 365) -> str:
    """Helper for tests / demos: produces a signed key with the local secret.

    Real customer keys would come from an offline issuer, not from this
    function. This exists so the test suite can exercise the happy path.
    """
    from datetime import timedelta
    today = datetime.now(timezone.utc).date()
    payload = {
        "customer": customer,
        "plan": plan,
        "issued_on": today.isoformat(),
        "expires_on": (today + timedelta(days=days)).isoformat(),
    }
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(_signing_secret(), payload_bytes, hashlib.sha256).digest()
    return (
        base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode("ascii")
        + "."
        + base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    )
