# Security policy

We treat security issues as first-class bugs. Thank you for taking the time
to report one.

## Supported versions

| Version  | Status              |
| -------- | ------------------- |
| `0.1.x`  | Active — patched    |
| `< 0.1`  | Unsupported         |

We maintain a single supported line. Once `0.2.x` ships, `0.1.x` will receive
critical-fix backports for 90 days and then drop to unsupported.

## Reporting a vulnerability

Email **security@enterprisecore.local** with:

- A description of the issue and the impact you observed
- Reproduction steps (commands, payload, expected vs. actual)
- The affected version (commit SHA or release tag if known)
- Whether the issue is already public

We try to acknowledge new reports within **two business days** and aim to
ship a fix or coordinated workaround within **30 days** for high-severity
issues and **90 days** for everything else. We will not disclose your
identity without consent and will credit you in the acknowledgements
section below once a fix has shipped, if you wish.

We follow a **90-day coordinated disclosure** window: from first acknowledged
report we will publish details (CVE, advisory, patch notes) no later than
90 days, even if a fix is not yet available, so users can take their own
mitigations. Earlier disclosure may happen if the vulnerability is already
being exploited in the wild.

Please **do not** report security issues through public GitHub issues,
pull requests, or community channels.

## Acknowledgements

Researchers who have responsibly disclosed issues to EnterpriseCore AI Suite:

_(none yet — be the first!)_

## Hardening posture

The backend ships with the following defenses enabled by default. Items
flagged "production" only apply when `APP_ENV=production`.

### Authentication and session

- Passwords hashed with **bcrypt** (configurable rounds, defaults to 12)
- JWT access + refresh tokens, **HS256**, signed by `SECRET_KEY`
- Refresh tokens stored as **HMAC-SHA256 hash** in the DB (one-way), indexed
  for O(log n) lookup; revoked rows are kept for audit
- Tokens delivered via:
  - `Authorization: Bearer …` for API / SDK clients
  - `httpOnly` cookies for browser clients — `__Host-` prefix in production
  - Access cookie defaults to `SameSite=strict`; refresh cookie defaults to
    `SameSite=lax` to allow same-site navigation flows
- **MFA (TOTP)** support per user, secret stored Fernet-encrypted

### Encryption at rest

- **Fernet** envelope encryption for PII columns (employee SSN, salary,
  customer phone/email)
- **BYO key Fernet** for stored AI provider keys (Anthropic, OpenAI) — the
  backend never logs or returns the plaintext key after first save
- Database file lives under `%LOCALAPPDATA%\EnterpriseCore AI Suite\storage\`
  on Windows / `~/.enterprisecore/storage/` on Linux/macOS

### Network and transport

- **Strict-Transport-Security** (production only): two-year `max-age`,
  `includeSubDomains`, `preload`
- **Content-Security-Policy** locked down to `default-src 'self'`, no
  inline scripts (`script-src 'self'`), object/embed blocked, `frame-ancestors
  'none'` on the API and admin app
- **X-Frame-Options: DENY** on everything except `/site/*` (the public
  marketing renderer, which downgrades to `SAMEORIGIN` so customers can
  embed their own site)
- **X-Content-Type-Options: nosniff**, **Referrer-Policy:
  strict-origin-when-cross-origin**, **Permissions-Policy** denying camera /
  geolocation / microphone / payment / USB / motion sensors
- **Cross-Origin-Opener-Policy: same-origin**,
  **Cross-Origin-Resource-Policy: same-site** (`cross-origin` for the
  embeddable `/widget.js` only)
- CORS pinned to the configured origin list — wildcard origins are not
  accepted in production

### Rate limiting

- Auth endpoints: 10/minute per IP on `/auth/login`, `/auth/register`;
  60/minute on `/auth/refresh`
- Per-module write bucket of **60/minute per IP** on every business
  endpoint group (`finance`, `hr`, `crm`, `projects`, `inventory`,
  `documents`, `communication`, `security`, `coding`, `ai`, `knowledge`,
  `marketing`, `academic`, `construction`, `auth`, `users`, `settings`,
  `notifications`, `license`) — GET/HEAD are exempt so reads are not
  affected
- Public webchat: 120/minute global IP cap plus a per-bot/per-session
  ceiling configured by the bot owner
- Marketing uploads: 5/minute per IP
- All limits use a sliding-window in-process limiter; restart resets the
  windows but the auth-related limits are short enough that this is
  acceptable for offline deployments

### Auditing

- `audit_log` table records every authentication event, mutation, and
  admin action with actor, IP, entity type/id, and a JSON detail blob
- Failed login attempts are tracked separately (`login_attempts`) for
  brute-force monitoring

### Upload hygiene

- Avatars: PNG/JPEG/WEBP only, hard-capped at 2 MB pre-decode, then
  thumbnailed to 512×512 and **re-encoded as PNG** to strip EXIF / GPS /
  ICC profile metadata
- Marketing media uploads use the same re-encode path
- Knowledge ingest enforces a configurable max size and validates MIME
  before storing

### Application surface

- No `dangerouslySetInnerHTML` in the SPA; user-supplied HTML is always
  rendered through DOMPurify or escaped by the template engine
- Marketing site renders with Jinja autoescape on
- All ORM access uses parameterised SQLAlchemy queries — no string-built
  SQL anywhere in the codebase
- Electron preload exposes a narrow, allow-listed IPC bridge; no
  `nodeIntegration`, `contextIsolation: true`

### Known limits

- Single-tenant: no per-tenant key isolation in this release
- HS256 (symmetric) JWT — keep `SECRET_KEY` truly secret; rotate via
  Alembic-aware key rotation script if compromised
- In-process rate-limiter: a multi-process / multi-worker deployment must
  switch `RATE_LIMIT_STORAGE` to Redis to share state
