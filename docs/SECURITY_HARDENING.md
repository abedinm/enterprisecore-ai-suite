# Security hardening

This document is the master reference for EnterpriseCore's security
posture. It pulls together every control the platform ships with, names
the threats they defend against, and tells operators what to turn on at
go-live.

Companion docs:

- [SECURITY.md](../SECURITY.md) — vulnerability disclosure policy.
- [SOC2_CONTROLS.md](SOC2_CONTROLS.md) — control-to-evidence mapping.
- [RBAC.md](RBAC.md) — role and permission model.
- [BYOK.md](BYOK.md) — bring-your-own-encryption-key for tenant data.
- [WEBHOOKS.md](WEBHOOKS.md) + [WEBHOOK_VERIFICATION_EXAMPLES.md](WEBHOOK_VERIFICATION_EXAMPLES.md) — webhook signing.

## Threat model

### In scope

| Threat                                                        | Mitigation summary                                              |
| ------------------------------------------------------------- | --------------------------------------------------------------- |
| Credential stuffing on `/api/v1/auth/login`                   | Per-IP rate limit + bcrypt + MFA + WebAuthn + lockout.          |
| Session hijack via XSS                                        | Strict CSP w/ per-request nonces; HttpOnly + SameSite cookies.  |
| CSRF on state-changing endpoints                              | SameSite=lax/strict cookies; double-submit token on form posts. |
| Tenant data crossing into another tenant via shared bug       | ORM auto-filter on every query bound to ContextVar.             |
| Webhook payload spoofing                                      | HMAC-SHA256 signature + ±5min replay window.                    |
| SSRF via a workflow that fetches URLs                         | Allowlist of public CIDR ranges; egress proxy when configured.  |
| SQL injection                                                 | SQLAlchemy parameterised queries everywhere.                    |
| Privilege escalation via permission tampering                 | Server-side permission check on every endpoint via decorator.   |
| Audit-log tampering                                           | Append-only table + optional SIEM stream-on-write.              |
| Secret exfiltration via logs                                  | Loguru filters scrub known secret patterns before emit.         |
| Replay of captured JWT after logout                           | Server-side revocation list checked on every request.           |
| Webhook receiver attacks (replay, sig forge)                  | Constant-time HMAC compare + timestamp drift check on receivers.|

### Out of scope (customer responsibility)

- Compromised end-user devices.
- TLS termination at the customer's load balancer.
- Physical security of the customer's data centre.
- Backup encryption at the storage provider (we recommend SSE-KMS).
- IdP-side credential management when SSO is in use.

## Authentication layers

EnterpriseCore supports six authentication mechanisms; admins enable
whichever combination matches their threat model.

| Mechanism            | Where                                            | Notes                                                    |
| -------------------- | ------------------------------------------------ | -------------------------------------------------------- |
| Password (bcrypt-12) | `POST /api/v1/auth/login`                        | Min 12 chars + zxcvbn score ≥ 3. Disable for admin orgs.|
| Magic link           | `POST /api/v1/auth/magic-link`                   | 15-minute TTL; one-time use; rotates JWT on consume.    |
| MFA (TOTP)           | Enforced post-login when user has a secret       | Backup codes one-time, scrypt-hashed.                    |
| WebAuthn / passkey   | `POST /api/v1/auth/webauthn/*`                   | Coordinated with `webauthn` agent — strongest factor.    |
| OIDC SSO             | `/api/v1/auth/oidc/login`                        | PKCE; state validated; ID token signature checked.       |
| SAML SSO             | `/api/v1/auth/saml/acs`                          | XMLSEC; assertion signature + audience + NotOnOrAfter.   |
| SCIM auto-provision  | `/scim/v2/Users` + `/scim/v2/Groups`             | Bearer token bound to a single tenant.                   |

### Recommended baseline

- Customer admin tenants: **WebAuthn required**, password disabled,
  SSO + SCIM with the IdP.
- Customer member tenants: **MFA required**, password allowed,
  SSO + SCIM with the IdP.

## Authorisation layers

1. **Roles + permissions.** Every endpoint declares a permission. The
   permission resolves to a role check via `app.core.permissions`. Custom
   roles are configurable per tenant under Settings → Security.
2. **Tenant isolation.** Every model row carries `tenant_id`; the
   `TenantMiddleware` puts the requesting tenant on a `ContextVar`, and
   `tenant_orm.install_tenant_orm_hooks()` injects a `WHERE tenant_id =
   :ctx` clause on every read + a `tenant_id` value on every write. The
   isolation invariant has dedicated tests in `tests/test_tenant_isolation.py`.
3. **IP allowlist.** Optional per-tenant CIDR allowlist enforced by
   `IPAllowlistMiddleware`. Bypass paths: `/api/health`, `/metrics`,
   `/widget.js`, `/site/*`, `/api/v1/auth/*`.
4. **Plan gating.** `app.core.plans.requires_plan()` decorates every
   module router. Disabled SKUs return a 402 with a structured error.
5. **Rate limiting.** Per-IP + per-tenant limits on every state-changing
   endpoint. Backed by `slowapi`; falls back from Redis to in-process
   when Redis is absent.

## Encryption

### At rest

- The application database is the customer's responsibility (Postgres
  TDE via the cloud provider's KMS is recommended).
- **Per-tenant DEK.** Sensitive PII columns (PII tags on the model)
  are encrypted with a per-tenant data encryption key. The DEKs are
  wrapped by the platform KEK; see [BYOK.md](BYOK.md) for the bring-
  your-own-KEK story.
- Uploaded files: SSE-S3 by default, SSE-KMS recommended for regulated
  industries.

### In transit

- TLS 1.3 only at the load balancer. TLS 1.2 is acceptable for
  legacy receivers (webhook deliveries), explicitly negotiated by httpx.
- HSTS `max-age=63072000; includeSubDomains; preload` in production.
- HTTP/2 supported end-to-end.

### BYOK / KMS

- Cloud KMS providers supported: AWS KMS, Google Cloud KMS, Azure Key
  Vault, HashiCorp Vault Transit. See `app/core/kms/` for the adapter
  layer.
- KEK rotation is online — re-wraps every DEK; takes <1 second per
  tenant.

## Audit logging + SIEM streaming

Every state-changing API call writes an `AuditEvent` row with:

- `tenant_id`, `user_id`, `action`, `entity_type`, `entity_id`
- `ip_address`, `user_agent`, `request_id`
- `before` and `after` JSON (truncated to 64 KiB)
- `created_at` (UTC)

The append-only stream can be forwarded to:

- Splunk HEC (HTTPS POST with token auth)
- Datadog Logs
- Generic HTTPS endpoint with HMAC-signed batches
- AWS S3 (hourly JSON lines)

Configuration is per-tenant under Settings → Compliance.

## Webhook security

EnterpriseCore signs every outbound webhook delivery:

- `X-EC-Signature: sha256=<hex>` — HMAC-SHA256 of the raw body using
  the subscription secret.
- `X-EC-Timestamp` — ISO 8601 UTC of when the event was emitted.
- `X-EC-Event-Id` — ULID, idempotency key.
- `X-EC-Event-Type` — canonical type from the catalog.

Receivers MUST:

1. Verify the signature with a constant-time compare.
2. Verify the timestamp is within ±5 minutes of their clock.
3. Dedupe by `X-EC-Event-Id` for at least 24 hours.

Code samples for six languages live in
[WEBHOOK_VERIFICATION_EXAMPLES.md](WEBHOOK_VERIFICATION_EXAMPLES.md).

For **inbound** webhooks (Stripe → EnterpriseCore, SAML callbacks, etc.)
the suite verifies vendor signatures and also accepts an optional per-
tenant CIDR allowlist for the inbound source IPs.

## CSP nonces

The `SecurityHeadersMiddleware` generates a fresh 16-byte base64 nonce on
every request and folds it into the `script-src` directive:

```
Content-Security-Policy: ... ;
  script-src 'self' 'nonce-9Z1tw1Pn4FbX4Y6Q2dKgvA==' ; ...
```

The same nonce is stashed on `request.state.csp_nonce` for templates
that render HTML at `/site/*`. Inline scripts emitted by those templates
must carry `nonce="{{ csp_nonce }}"` to execute.

`'unsafe-inline'` is still permitted on `style-src` because Tailwind
injects style tags at runtime. Migrating styles to a nonce too is on the
roadmap — it requires a Tailwind build that emits nonces on its runtime
style tags. Tracked as a follow-up; see "Common misconfigurations to
avoid" below for what NOT to do in the meantime.

## Secret management

- Operators inject secrets via environment variables. The container
  image NEVER bakes secrets into a layer.
- Cloud secret stores (AWS Secrets Manager, GCP Secret Manager, K8s
  Secrets, HashiCorp Vault) are first-class — the Helm chart supports
  every one.
- `SECRET_KEY` rotation policy: every 90 days; supports overlapping
  active and previous key with the `SECRET_KEY_FALLBACK` env var so
  active JWTs don't bounce.
- Per-subscription webhook secrets are rotatable from the dashboard
  (`POST /api/v1/webhooks/subscriptions/{id}/rotate-secret`).
- The Stripe webhook secret + SCIM bearer tokens are stored encrypted
  with the tenant DEK; the cleartext is shown once on creation only.

## Vulnerability disclosure

See [SECURITY.md](../SECURITY.md) at the repo root. Headline policy:

- Coordinated disclosure with a 90-day deadline.
- security@enterprisecore.com is monitored 24/7.
- Hall-of-fame credits + cash bounties for high-severity reports.
- No legal action against good-faith researchers.

## Common misconfigurations to avoid

1. **Re-adding `'unsafe-inline'` to `script-src` "just for now".** Once
   the directive is present the entire benefit of the CSP collapses.
   Use nonces or external script files.
2. **Logging the JWT into application logs.** The `loguru` filter scrubs
   `Authorization` headers, but custom logging additions might bypass
   it — review log statements that handle headers.
3. **Disabling tenant ORM hooks for performance.** Don't. The auto-
   filter is a single equality predicate; its cost is dwarfed by the
   underlying query and it is the single most important data-isolation
   control.
4. **Reading the webhook secret out of the database in plaintext.** The
   secret only appears in plaintext on the create response; subsequent
   reads return a placeholder. Don't add an admin endpoint that
   surfaces it.
5. **Allowing `*` as the SCIM bearer's tenant binding.** Each SCIM
   token must be bound to exactly one tenant.
6. **Pointing the audit stream at an HTTP (non-TLS) endpoint.** The
   audit stream contains highly-sensitive payloads — only HTTPS
   destinations are accepted.
7. **Setting `CORS_ALLOW_ORIGINS=*` in production.** Use exact origins.
   The widget asset and public chat endpoints already manage their own
   permissive CORS; you don't need a global `*`.
8. **Leaving `EC_ALLOW_DESTRUCTIVE_MIGRATIONS` set globally.** Set it
   only during the specific migration window that needs it, then unset.

## Production security checklist

Run this before flipping the public DNS. Re-audit quarterly.

- [ ] TLS 1.3 only at the LB; weak ciphers off; OCSP stapling on.
- [ ] HSTS preloaded.
- [ ] SECRET_KEY rotated from any example value; rotation policy in
      place.
- [ ] SSO enforced for admin tenant; password login disabled for
      admins.
- [ ] MFA required for every privileged role; WebAuthn rolled out to
      admins.
- [ ] Per-tenant IP allowlist configured where the customer has fixed
      egress.
- [ ] Audit stream wired up to the customer's SIEM and tested.
- [ ] Webhook secrets rotated at least once since first boot.
- [ ] CSP nonce middleware verified live (`curl -I` shows
      `script-src 'self' 'nonce-...'`).
- [ ] Backups verified by an actual restore in the last 90 days.
