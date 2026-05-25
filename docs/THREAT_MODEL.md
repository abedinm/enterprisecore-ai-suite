# EnterpriseCore AI — Threat Model

Last updated: 2026-05-23. Owner: security@enterprisecore.app.

This document follows the STRIDE framework. It is reviewed quarterly and
on every release that introduces a new trust boundary, integration, or
externally-reachable surface.

## 1. Scope

In scope:

- The FastAPI backend (`backend/app/`).
- The React/Vite/Electron frontend (`frontend/src/`).
- The license server interaction (`backend/app/core/remote_license.py`).
- The marketing site renderer at `/site/*`.
- The embeddable web-chat widget at `/widget.js`.
- The SCIM/OIDC/SAML/WebAuthn provisioning + identity surfaces.

Out of scope:

- The customer's reverse proxy (Nginx/Cloudflare/AWS ALB). We document
  the headers and paths we depend on; physical hardening of those tiers
  is the operator's responsibility.
- Third-party AI providers (Anthropic, OpenAI, Ollama) once a request
  has left our process. We minimise data passed and document
  per-provider opt-outs.
- Code-quality issues that do not have a security impact.

## 2. Trust boundaries

```
       Internet
          |
   ┌──────▼──────┐         ┌────────────────────────────┐
   │ Reverse     │  TLS    │  Browser (SPA, Electron)   │
   │ proxy +     │ ───────▶│  - SameSite cookies         │
   │ TLS term    │         │  - X-CSRF-Token header      │
   └──────┬──────┘         └─────────────┬──────────────┘
          │  HTTP/1.1                    │  JSON / FormData
   ┌──────▼──────────────────────────────▼──────────────┐
   │ FastAPI app                                         │
   │  - SecurityHeadersMiddleware (CSP, HSTS, COOP)      │
   │  - IPAllowlistMiddleware                            │
   │  - TenantMiddleware → ContextVar                    │
   │  - CSRFMiddleware (double-submit)                   │
   │  - PrometheusMiddleware / RequestIDMiddleware       │
   │  - SlowAPI rate limit decorator on hot routes       │
   │  - Application routers                              │
   └──────┬──────────────┬──────────────┬───────────────┘
          │              │              │
   ┌──────▼──────┐  ┌────▼────┐  ┌──────▼──────┐
   │ Postgres /  │  │ Redis   │  │ License     │
   │ SQLite      │  │ (rl,    │  │ server      │
   │ (encrypted  │  │ realtime│  │ (Ed25519-   │
   │  columns)   │  │  pubsub)│  │  signed)    │
   └─────────────┘  └─────────┘  └─────────────┘
```

Each arrow crossing a box boundary is a trust boundary subject to
authentication, authorisation, and validation. Below: per-arrow STRIDE.

## 3. STRIDE matrix (selected high-signal entries)

### Spoofing

| Threat | Mitigation |
|---|---|
| Attacker spoofs a legit user via stolen JWT | JWT bound to user via `sub`, short-lived (60 min), refresh on device fingerprint match only. |
| Attacker presents a forged refresh token from a different browser | `device_fingerprint = HMAC(secret, UA-family + IP/24)`. Mismatch revokes ALL sessions and logs `refresh_token_device_mismatch`. |
| Attacker spoofs the license server | License server claims must be Ed25519-signed; pubkey pinned at build time. HTTPS alone is NOT trusted. |
| Attacker spoofs an SSO IdP response | SAML signed assertion + relay state cookie (CSRF + nonce). OIDC: signed state + nonce + JWKS-verified ID-token. |
| Attacker spoofs Stripe webhook | Stripe-Signature header verified with `STRIPE_WEBHOOK_SECRET` and `STRIPE_WEBHOOK_TOLERANCE_SECONDS`. |

### Tampering

| Threat | Mitigation |
|---|---|
| Modification of audit-log rows | `AuditLog` rows are append-only via the ORM service layer; no UPDATE endpoint. Optional Postgres trigger to enforce in DB. |
| Tampered license cache on disk | Cache embeds the signed envelope; re-verified on every boot via the pinned Ed25519 pubkey. |
| Tampered marketing site renderer output | Output is server-rendered with strict CSP; user content sanitised with `bleach`. |
| Edits to `password_hash` column to elevate | DB role used by app has no direct UPDATE on `users.password_hash` outside of the change-password endpoint (DBA controls this). |

### Repudiation

| Threat | Mitigation |
|---|---|
| User denies performing an action | Every state-changing endpoint emits an `AuditLog` row with actor_id + IP + JSON detail. Audit log is tenant-scoped + indexed on actor + action + entity. |
| Operator denies a config change | Settings writes audit-logged. SCIM provisioning writes audit-logged. |

### Information disclosure

| Threat | Mitigation |
|---|---|
| Cross-tenant data leak | `TenantMiddleware` sets `tenant_id` on a ContextVar; `tenant_orm.py` adds a WHERE filter to every SELECT. Tests in `tests/test_tenant_isolation.py` exercise the boundary. Any service using raw SQL must call `tenant_scope()` explicitly. |
| Secrets exposure in URLs / logs | All Bearer tokens use the `Authorization` header; cookies are httpOnly. Loguru is configured to scrub `password`, `secret_key`, `encryption_key`, `refresh_token`, `access_token`. Sentry has the same scrubbers. |
| Secrets exposure via error responses | Production handler returns `code` + sanitised `detail`. Internal exceptions surface as `code="internal_error"` with no stack to the client. Stack traces go to Sentry. |
| AI prompt exfiltration | Per-user 24h $-cap on paid providers; per-tenant cap available via `ai_daily_usd_limit_per_tenant`. Prompts NOT persisted to AI provider memory; Anthropic `metadata.user_id` set to a tenant-stable hash, not the user email. |
| Avatar / upload metadata leak | Avatars re-encoded as PNG, resized to 512×512, EXIF stripped. Other uploads sandboxed under `storage/uploads`. |
| License server learning customer behaviour | License server only receives `key`, `machine_id`, `app_version`. No telemetry payload. |

### Denial of service

| Threat | Mitigation |
|---|---|
| Auth brute-force | `slowapi` 10/min on `/auth/login` and `/auth/register` per IP. Account-lockout after 10 failed attempts in 15 min (configurable). |
| API abuse from one tenant | Per-tenant rate limit roadmap (current: per-IP + per-user). Redis-backed for multi-replica deploys. |
| Large file uploads | 100 MB max on Knowledge Hub ingest; 2 MB on avatars; reverse proxy should enforce a smaller `client_max_body_size`. |
| Slowloris / connection holding | uvicorn `--timeout-keep-alive` and reverse-proxy timeouts; documented in `docs/PERFORMANCE.md`. |
| AI spend bomb | $5/user/24h hard cap on paid providers (Anthropic/OpenAI). Ollama exempt. |
| WebSocket flood | Per-connection auth + per-connection message budget. |

### Elevation of privilege

| Threat | Mitigation |
|---|---|
| Role-tampering via JWT | Role is read fresh from DB inside `get_current_user`; the `role` claim is informational only. |
| SCIM provisioning of admin users | SCIM token is per-tenant, never global; admin role must be explicitly assigned in the tenant's user-roles UI. |
| WebAuthn cred binding bypass | Credentials bind to `(rp_id, user_handle)`; assertion verifies the stored public key. AAGUID is logged. |
| Permission catalog hole | `require_permission()` is the only authorised check helper; permission keys are seeded by migration 0017 — adding a new endpoint without registering a key fails the catalog test. |
| Tenant impersonation via header | Operators may set `X-Tenant-Override` only when the JWT carries the `tenant_admin` permission for the source tenant AND the target tenant; logged on every use. |

## 4. Risks knowingly accepted

These exist in the threat model but have not been remediated yet, with
reasoning. Listed publicly so customers can weigh them.

1. **CSP `style-src 'unsafe-inline'`** — Tailwind injects styles at
   runtime. We will move to nonce'd styles once Tailwind ships a
   nonce-friendly engine; tracked in `docs/SECURITY_HARDENING.md`.
2. **In-process APScheduler in multi-replica deploys** — leader
   election via Postgres advisory lock is implemented but optional. If
   `LEADER_ELECTION=off` the operator accepts duplicate-fire risk on
   idempotent cleanup jobs.
3. **slowapi 0.1.9** — pinned old because of a known signature
   introspection regression in 0.1.10. We re-evaluate every release.

## 5. Review cadence

- Quarterly: full STRIDE pass with the on-call security engineer.
- Per release: diff `app/api/v1/endpoints/` and `app/services/` against
  the previous tag; new endpoints must reference an STRIDE row above.
- Annual: external penetration test (vendor: TBD pre-1.0).

## 6. Reporting

See `SECURITY.md` for the responsible-disclosure process.
