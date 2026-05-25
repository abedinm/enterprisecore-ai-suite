"""Device fingerprinting for refresh-token theft detection.

A "device" is identified by the tuple ``(user_agent_class, ip_network_24)``
hashed with HMAC-SHA256 keyed by the application secret. The result is a
short, irreversible token that:

* survives the small noise of subnet hopping (we bucket IPv4 to /24,
  IPv6 to /48) so a refresh from the office DHCP pool still verifies,
* survives Chrome point-version bumps because we strip the version,
* fails-closed against an attacker on a different ISP / different
  browser — they cannot forge a matching fingerprint without the secret.

We deliberately avoid storing the raw User-Agent or IP for privacy. The
fingerprint is the only thing persisted; the original strings are not.

Trade-offs
----------

* Mobile/tethered users moving between cell-tower subnets across a /24
  boundary will be challenged (treated as a new device). They are
  prompted to re-authenticate. That's the right default — better one
  inconvenient re-login than letting a stolen token roam free.
* Privacy-respecting browsers that randomise the User-Agent string per
  visit (Brave's "Strict" mode) will fingerprint inconsistently. We
  document the trade-off and recommend SSO/passkeys for those users.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re

from app.core.config import settings


_UA_VERSION_RE = re.compile(r"\d+(\.\d+)+")


def _ua_class(user_agent: str | None) -> str:
    """Bucket the User-Agent down to a stable family/major name.

    The full UA string changes too often (every Chrome auto-update) to bind a
    refresh token to. We strip version numbers and lowercase so two visits
    from "the same browser" hash identically.
    """
    if not user_agent:
        return "unknown"
    cleaned = _UA_VERSION_RE.sub("", user_agent)
    return cleaned.lower().strip()[:200]


def _ip_bucket(ip: str | None) -> str:
    """Bucket the IP to its containing /24 (IPv4) or /48 (IPv6).

    Cellular carriers and corporate VPNs commonly hand out addresses within
    a /24; bucketing avoids spurious "device mismatch" warnings every time
    DHCP rotates the last octet.
    """
    if not ip:
        return "no-ip"
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return "bad-ip"
    if isinstance(parsed, ipaddress.IPv4Address):
        net = ipaddress.ip_network(f"{ip}/24", strict=False)
    else:
        net = ipaddress.ip_network(f"{ip}/48", strict=False)
    return str(net)


def fingerprint(user_agent: str | None, ip: str | None) -> str:
    """Return the stable HMAC-SHA256 fingerprint for this device."""
    material = f"{_ua_class(user_agent)}|{_ip_bucket(ip)}"
    mac = hmac.new(
        settings.secret_key.encode("utf-8"),
        material.encode("utf-8"),
        hashlib.sha256,
    )
    return mac.hexdigest()[:48]


def device_label(user_agent: str | None, ip: str | None) -> str:
    """Human-friendly label shown in the Sessions list (NOT used for auth).

    Inferred at issue time and stored alongside the fingerprint. We avoid
    storing the raw UA — this label is one line of summary text only.
    """
    ua = (user_agent or "").lower()
    if "edg/" in ua:
        browser = "Edge"
    elif "chrome/" in ua:
        browser = "Chrome"
    elif "firefox/" in ua:
        browser = "Firefox"
    elif "safari/" in ua and "chrome/" not in ua:
        browser = "Safari"
    else:
        browser = "Browser"
    if "windows" in ua:
        os_name = "Windows"
    elif "mac os" in ua or "macintosh" in ua:
        os_name = "macOS"
    elif "android" in ua:
        os_name = "Android"
    elif "iphone" in ua or "ipad" in ua or "ios" in ua:
        os_name = "iOS"
    elif "linux" in ua:
        os_name = "Linux"
    else:
        os_name = "Unknown OS"
    net = _ip_bucket(ip)
    return f"{browser} on {os_name} ({net})"
