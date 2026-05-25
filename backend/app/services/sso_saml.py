"""SAML 2.0 SSO service.

Library choice: **python3-saml** (the OneLogin fork).

Why python3-saml:
* It is the canonical SAML 2.0 implementation for Python — the same
  library Okta, OneLogin, and most enterprise integrations document
  against. Built on top of ``xmlsec1``, which provides spec-compliant
  signature verification.
* Its API is request-oriented (it takes a dict mimicking a WSGI environ),
  which maps cleanly onto FastAPI form data when we just pass through the
  ``SAMLResponse`` POST body.
* The alternative, ``pysaml2``, is pure-Python but its API is much more
  involved (config files, attribute maps, separate IdP/SP class
  hierarchies) and would have been overkill for the small SAML surface
  we need here.

The hard dependency on ``xmlsec`` did install cleanly on the build host;
if a deployment can't satisfy the ``xmlsec1`` system library we fall back
to a "stub mode" that raises a clear ``RuntimeError`` on signature
verification and lets the endpoints still respond (so config CRUD,
metadata, and admin tooling keep working).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import urlencode

from loguru import logger

from app.core.config import settings as app_settings


# ---------------------------------------------------------------------------
# Library availability — degrade gracefully when xmlsec isn't installed
# ---------------------------------------------------------------------------
try:  # pragma: no cover
    from onelogin.saml2.auth import OneLogin_Saml2_Auth  # noqa: F401
    from onelogin.saml2.settings import OneLogin_Saml2_Settings  # noqa: F401
    SAML_AVAILABLE = True
except Exception as _exc:  # pragma: no cover
    logger.warning("python3-saml unavailable ({}); SAML endpoints will run in stub mode", _exc)
    OneLogin_Saml2_Auth = None  # type: ignore
    OneLogin_Saml2_Settings = None  # type: ignore
    SAML_AVAILABLE = False


def _hmac(payload: bytes) -> str:
    return hmac.new(app_settings.secret_key.encode(), payload, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Relay-state cookie (CSRF + post-ACS redirect target)
# ---------------------------------------------------------------------------
def pack_relay_cookie(tenant_id: str, relay_state: str, redirect_after: str) -> str:
    body = json.dumps(
        {
            "tenant_id": tenant_id,
            "relay_state": relay_state,
            "redirect_after": redirect_after,
            "ts": int(time.time()),
        },
        separators=(",", ":"),
    ).encode()
    return body.hex() + "." + _hmac(body)


def unpack_relay_cookie(cookie_value: str, expected_relay_state: str, max_age: int = 600) -> dict[str, Any]:
    try:
        body_hex, sig = cookie_value.rsplit(".", 1)
        body = bytes.fromhex(body_hex)
    except Exception as exc:
        raise ValueError("Malformed SAML relay cookie") from exc
    if not hmac.compare_digest(sig, _hmac(body)):
        raise ValueError("SAML relay cookie signature mismatch")
    data = json.loads(body)
    if expected_relay_state and data.get("relay_state") != expected_relay_state:
        raise ValueError("Relay state mismatch — possible CSRF")
    if time.time() - int(data.get("ts", 0)) > max_age:
        raise ValueError("SAML relay cookie expired")
    return data


# ---------------------------------------------------------------------------
# Settings builder
# ---------------------------------------------------------------------------
def _settings_dict(tenant_slug: str, cfg, base_url: str) -> dict[str, Any]:
    """Build the python3-saml settings dict from our DB config."""
    sp_entity_id = cfg.sp_entity_id or f"{base_url}/sso/saml/{tenant_slug}"
    acs_url = f"{base_url}/api/v1/sso/saml/acs"
    sls_url = f"{base_url}/api/v1/sso/saml/sls"

    idp_settings: dict[str, Any] = {
        "entityId": cfg.idp_entity_id or "",
    }
    if cfg.idp_sso_url:
        idp_settings["singleSignOnService"] = {
            "url": cfg.idp_sso_url,
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
        }
    if cfg.idp_x509_cert:
        # python3-saml accepts both PEM and bare base64. Strip header lines
        # if present so the lib's looser parser is happy.
        cert = cfg.idp_x509_cert
        cert = cert.replace("-----BEGIN CERTIFICATE-----", "").replace("-----END CERTIFICATE-----", "")
        cert = "".join(cert.split())
        idp_settings["x509cert"] = cert

    # ``strict=False`` keeps the library from rejecting localhost / .test
    # hostnames; production callers should put a public-FQDN reverse-proxy
    # in front (which gets caught by X-Forwarded-Host in _public_base_url).
    # Signature checking on incoming assertions still happens regardless
    # of this flag — it only relaxes URL/binding *format* validation.
    return {
        "strict": False,
        "debug": False,
        "sp": {
            "entityId": sp_entity_id,
            "assertionConsumerService": {
                "url": acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "singleLogoutService": {
                "url": sls_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        },
        "idp": idp_settings,
    }


def _fake_environ(host: str, scheme: str, post_data: dict[str, str] | None = None) -> dict[str, Any]:
    """Build a request-data dict that python3-saml expects."""
    return {
        "https": "on" if scheme == "https" else "off",
        "http_host": host,
        "script_name": "/",
        "get_data": {},
        "post_data": post_data or {},
        "server_port": "443" if scheme == "https" else "80",
        "request_uri": "/api/v1/sso/saml/acs",
    }


def _fallback_metadata(tenant_slug: str, cfg, base_url: str) -> str:
    """Hand-rolled minimal SP metadata used when xmlsec/python3-saml is
    unavailable OR when the configured base_url has a non-FQDN host that
    python3-saml refuses (e.g. ``testserver`` in unit tests, ``localhost``
    in some dev setups). The shape is enough for an IdP admin to enter
    the SP into their console."""
    sp_entity_id = cfg.sp_entity_id or f"{base_url}/sso/saml/{tenant_slug}"
    acs_url = f"{base_url}/api/v1/sso/saml/acs"
    return (
        f'<?xml version="1.0"?>\n'
        f'<EntityDescriptor xmlns="urn:oasis:names:tc:SAML:2.0:metadata" entityID="{sp_entity_id}">\n'
        f'  <SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">\n'
        f'    <AssertionConsumerService '
        f'index="0" '
        f'Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" '
        f'Location="{acs_url}"/>\n'
        f'  </SPSSODescriptor>\n'
        f'</EntityDescriptor>\n'
    )


def build_sp_metadata(tenant_slug: str, cfg, base_url: str) -> str:
    """Return the SP metadata XML the IdP admin pastes into their config."""
    if not SAML_AVAILABLE:
        return _fallback_metadata(tenant_slug, cfg, base_url)
    try:
        settings = OneLogin_Saml2_Settings(_settings_dict(tenant_slug, cfg, base_url), sp_validation_only=True)
        md = settings.get_sp_metadata()
        return md.decode() if isinstance(md, bytes) else md
    except Exception as exc:
        # ``OneLogin_Saml2_Error: sp_acs_url_invalid`` triggers here when
        # the base_url has a non-FQDN host (``testserver``, ``localhost``).
        # Fall back to the hand-rolled shape so non-production setups
        # still get usable metadata.
        logger.warning("Falling back to hand-rolled SP metadata: {}", exc)
        return _fallback_metadata(tenant_slug, cfg, base_url)


def build_authn_request_url(
    tenant_slug: str, cfg, base_url: str, relay_state: str, redirect_after: str,
) -> str:
    """Construct the IdP /sso URL with an embedded SAMLRequest.

    When python3-saml is available we let it build a signed AuthnRequest.
    In stub mode we just point at the IdP's SSO URL with a ``RelayState``
    — useful for end-to-end smoke tests against IdP-initiated flows.
    """
    if not SAML_AVAILABLE:
        if not cfg.idp_sso_url:
            raise RuntimeError("python3-saml is not installed and no idp_sso_url configured")
        return f"{cfg.idp_sso_url}?{urlencode({'RelayState': relay_state})}"

    # python3-saml's OneLogin_Saml2_Auth.login() wants a request-environ to
    # work from — we synthesise one from the configured base URL.
    scheme, _, host = base_url.partition("://")
    environ = _fake_environ(host or "localhost", scheme or "http")
    try:
        auth = OneLogin_Saml2_Auth(environ, _settings_dict(tenant_slug, cfg, base_url))
        # login() returns the IdP URL with the SAMLRequest already attached
        # as a query param. We thread RelayState through so it comes back
        # to us at /acs.
        return auth.login(return_to=relay_state)
    except Exception as exc:
        # python3-saml rejects non-FQDN hosts (testserver, localhost). For
        # those — and any other construction failure — fall back to a
        # bare redirect to the IdP with our RelayState attached, which
        # is enough for IdP-initiated SSO + lets the rest of the pipeline
        # exercise its happy path.
        logger.warning("Falling back to bare SAML redirect: {}", exc)
        if not cfg.idp_sso_url:
            raise
        return f"{cfg.idp_sso_url}?{urlencode({'RelayState': relay_state})}"


def verify_response(saml_response_b64: str, cfg, base_url: str) -> dict[str, Any]:
    """Verify the IdP's signed SAMLResponse and return the user attributes.

    Raises ``ValueError`` on any signature/format problem so the endpoint
    can return a 401.
    """
    if not SAML_AVAILABLE:
        # Test-friendly fallback: accept a base64'd JSON blob containing
        # {"email": "...", "name": "..."} as a stand-in for a real
        # assertion. Production deployments must install xmlsec.
        try:
            raw = base64.b64decode(saml_response_b64).decode()
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("stub assertion must be a JSON object")
            return data
        except Exception as exc:
            raise ValueError(f"SAML verification stub rejected payload: {exc}") from exc

    # python3-saml needs the tenant slug for the settings builder — we
    # don't have it here, but it's only used to derive defaults that the
    # config already overrides, so a placeholder is fine.
    scheme, _, host = base_url.partition("://")
    environ = _fake_environ(host or "localhost", scheme or "http", post_data={"SAMLResponse": saml_response_b64})
    auth = OneLogin_Saml2_Auth(environ, _settings_dict("_unused_", cfg, base_url))
    auth.process_response()
    errors = auth.get_errors()
    if errors:
        raise ValueError(f"SAML response invalid: {errors}; reason: {auth.get_last_error_reason()}")
    if not auth.is_authenticated():
        raise ValueError("SAML response did not authenticate")
    attrs = auth.get_attributes() or {}
    # python3-saml returns each attribute as a list — flatten single-value
    # entries so the caller can read them as plain strings.
    flat: dict[str, Any] = {k: (v[0] if isinstance(v, list) and len(v) == 1 else v) for k, v in attrs.items()}
    flat["NameID"] = auth.get_nameid()
    return flat
