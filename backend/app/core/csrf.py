"""CSRF defence — double-submit cookie pattern.

Why double-submit and not synchroniser-token?

* The synchroniser pattern needs server-side per-session storage. With
  multi-replica deploys that means Redis or sticky sessions.
* Double-submit only needs a cookie + a request header; no server state.
* SameSite=Lax on the access cookie already blocks the vast majority of
  CSRF (cross-site POSTs do not send the cookie). The CSRF token catches
  the residual cases: subdomain takeovers, browsers with broken SameSite
  enforcement, and the small set of legitimate top-level GET-initiated
  state changes we have to defend in depth.

Flow
----

1. ``/auth/login`` (and ``/auth/refresh``) issue a ``csrf_token`` cookie via
   :func:`issue_csrf_cookie`. The cookie is intentionally NOT ``httpOnly`` —
   the frontend must read it to mirror it into the ``X-CSRF-Token`` header.
2. This middleware enforces, on every state-changing request authenticated
   via cookie:

   - request carries an ``X-CSRF-Token`` header
   - the header value equals the ``csrf_token`` cookie value
   - both are non-empty

3. Bearer-authenticated requests (Electron + API/SDK clients) are exempt —
   they can't be tricked into mounting a cross-origin attack with a header
   they don't possess.

Exempt paths
------------

* ``/api/v1/auth/login``    — there's no session yet
* ``/api/v1/auth/register`` — there's no session yet
* ``/api/v1/auth/refresh``  — verified separately by the refresh-token JWT
* ``/api/v1/auth/magic-link/*`` — magic-link consumption is gated by the
  one-time signed token, not session cookies
* ``/api/v1/auth/sso/*``    — SAML/OIDC have their own state-cookie defence
* ``/scim/v2/*``            — bearer-token only, never cookie-authenticated
* ``/stripe/webhook``       — webhook signature is the auth
* ``/api/v1/webhooks/*``    — webhook signatures
* ``/widget.js`` and ``/site/*`` — public, unauthenticated
"""
from __future__ import annotations

import hmac
import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
CSRF_TOKEN_BYTES = 32

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Prefixes that bypass CSRF enforcement. These are either unauthenticated,
# rely on a different auth scheme (bearer, webhook signature), or are
# pre-session endpoints where there's nothing to defend yet.
EXEMPT_PREFIXES: tuple[str, ...] = (
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/api/v1/auth/logout",   # logout must always be reachable; blocking it is worse than any CSRF risk
    "/api/v1/auth/magic-link",
    "/api/v1/auth/sso",
    "/api/v1/auth/webauthn",
    # Pre-session tenant endpoints — no auth cookie yet, nothing to defend.
    "/api/v1/tenants/signup",
    "/api/v1/tenants/accept-invite",
    # SSO callback / SAML ACS endpoints land back here without our cookie set;
    # they validate state via their own one-time tokens.
    "/api/v1/sso/oidc/callback",
    "/api/v1/sso/saml/acs",
    # WebAuthn authentication ceremony — gated by challenge state, not CSRF.
    "/api/v1/webauthn/authenticate/begin",
    "/api/v1/webauthn/authenticate/finish",
    # Webhook signatures (Stripe, Slack, DocuSign, GitHub) are the auth.
    "/api/v1/webhooks",
    "/api/v1/billing/stripe-webhook",
    "/api/v1/stripe",
    "/stripe/webhook",
    # SCIM uses bearer tokens, never cookies.
    "/scim/v2",
    "/widget.js",
    "/site/",
    "/files/",
)


def issue_csrf_cookie(response: Response, *, secure: bool, samesite: str = "lax") -> str:
    """Mint a fresh CSRF token and write it to *response* as a readable cookie.

    Returns the token so callers (e.g. login) can also embed it in the JSON
    payload if they want — handy for SPA bootstrap.
    """
    token = secrets.token_urlsafe(CSRF_TOKEN_BYTES)
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        max_age=60 * 60 * 12,  # 12h — token rotates on next login/refresh
        httponly=False,        # MUST be readable so the SPA can echo it
        samesite=samesite,
        secure=secure,
        path="/",
    )
    return token


def clear_csrf_cookie(response: Response) -> None:
    """Drop the CSRF cookie on logout."""
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


def _path_is_exempt(path: str) -> bool:
    for p in EXEMPT_PREFIXES:
        if path == p or path.startswith(p):
            return True
    return False


class CSRFMiddleware(BaseHTTPMiddleware):
    """Enforce the double-submit cookie pattern for cookie-authenticated requests.

    The check is deliberately narrow:

    * Read-only methods (GET/HEAD/OPTIONS) never need a token.
    * Requests carrying an ``Authorization: Bearer`` header bypass — bearer
      auth is not vulnerable to CSRF.
    * Exempt paths bypass entirely.
    * Everything else MUST present a header equal to the cookie.

    Compare with :func:`hmac.compare_digest` to neutralise timing attacks.
    """

    def __init__(self, app: ASGIApp, *, enabled: bool = True) -> None:
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)
        if request.method not in MUTATING_METHODS:
            return await call_next(request)
        if _path_is_exempt(request.url.path):
            return await call_next(request)

        # Bearer auth is CSRF-immune: a cross-origin attacker can't read or
        # set the Authorization header without an already-XSS'd page. We let
        # the auth dependency validate the token; we just skip CSRF here.
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return await call_next(request)

        cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
        header_token = request.headers.get(CSRF_HEADER_NAME, "")
        if (
            not cookie_token
            or not header_token
            or not hmac.compare_digest(cookie_token, header_token)
        ):
            # Localise the user-facing detail; the `code` stays English so
            # SDK clients (and tests) can switch on it.
            try:
                from app.core.i18n import parse_accept_language, translate
                locale = parse_accept_language(request.headers.get("accept-language"))
                detail = translate("errors.csrf_failed", locale)
            except Exception:  # pragma: no cover
                detail = "Your session needs to refresh — reload the page and try again."
            return JSONResponse(
                status_code=403,
                content={"detail": detail, "code": "csrf_failed"},
            )
        return await call_next(request)
