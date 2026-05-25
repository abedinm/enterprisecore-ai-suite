# SOC 2 Control Mapping — EnterpriseCore AI Suite

This document maps each AICPA 2017 Trust Service Criteria (TSC) point
relevant to a SaaS deployment of EnterpriseCore to the specific feature,
configuration, or evidence trail that satisfies it. It is intended for
auditors and CISOs evaluating EnterpriseCore for SOC 2 Type I or Type II
attestation, and for engineering teams maintaining the controls.

The Trust Service Criteria covered are:

- **CC1** — Control Environment
- **CC2** — Communication & Information
- **CC3** — Risk Assessment
- **CC4** — Monitoring Activities
- **CC5** — Control Activities
- **CC6** — Logical & Physical Access
- **CC7** — System Operations
- **CC8** — Change Management
- **CC9** — Risk Mitigation

A1 (Availability) and C1 (Confidentiality) overlay controls are noted
under their respective common criteria.

---

## CC1 — Control Environment

| ID | Control                                              | EnterpriseCore implementation                                  | Evidence                                                     |
|----|------------------------------------------------------|----------------------------------------------------------------|--------------------------------------------------------------|
| CC1.1 | Demonstrate commitment to integrity & ethics      | Code of Conduct in repo `CODE_OF_CONDUCT.md`; CONTRIBUTING.md  | Files at repo root                                           |
| CC1.2 | Board independence & oversight                    | Out of scope for the software product itself                   | Customer-side                                                |
| CC1.3 | Structures + reporting lines                      | Out of scope                                                   | Customer-side                                                |
| CC1.4 | Commitment to attracting/developing/retaining     | Out of scope                                                   | Customer-side                                                |
| CC1.5 | Accountability via job descriptions               | Out of scope                                                   | Customer-side                                                |

## CC2 — Communication & Information

| ID | Control                                              | EnterpriseCore implementation                                                       | Evidence                                                     |
|----|------------------------------------------------------|-------------------------------------------------------------------------------------|--------------------------------------------------------------|
| CC2.1 | Information quality                                | Strong typing (Pydantic) + DB constraints + 535+ tests                              | `tests/`, schemas under `app/schemas/`                       |
| CC2.2 | Internal communication of security responsibilities | `SECURITY.md` at repo root + this file                                              | Files                                                        |
| CC2.3 | External communication                             | `SECURITY.md` includes responsible-disclosure contact; status page documented       | `SECURITY.md`                                                |

## CC3 — Risk Assessment

| ID | Control                                              | EnterpriseCore implementation                                                       | Evidence                                                     |
|----|------------------------------------------------------|-------------------------------------------------------------------------------------|--------------------------------------------------------------|
| CC3.1 | Specifies objectives                              | Roadmap in `docs/ARCHITECTURE.md`                                                   | Doc                                                          |
| CC3.2 | Identifies + analyzes risks                       | Threat model section in `SECURITY.md`; dependency audit via `pip-audit` in CI       | CI workflow + `SECURITY.md`                                  |
| CC3.3 | Fraud risk                                        | Audit log of every sensitive action + tamper-evident ordering                       | `audit_logs` table                                           |
| CC3.4 | Identifies/assesses changes                       | Migration review required in PR template                                            | `.github/PULL_REQUEST_TEMPLATE.md`                           |

## CC4 — Monitoring

| ID | Control                                              | EnterpriseCore implementation                                                       | Evidence                                                     |
|----|------------------------------------------------------|-------------------------------------------------------------------------------------|--------------------------------------------------------------|
| CC4.1 | Ongoing/separate evaluations                      | Prometheus metrics on every endpoint; Sentry error reporting; OTel traces           | `app/core/observability.py`, `/metrics` endpoint              |
| CC4.2 | Communicates deficiencies                         | Audit stream destinations push every event to the customer's SIEM in real time      | `app/services/audit_streamer.py`                             |

## CC5 — Control Activities

| ID | Control                                              | EnterpriseCore implementation                                                       | Evidence                                                     |
|----|------------------------------------------------------|-------------------------------------------------------------------------------------|--------------------------------------------------------------|
| CC5.1 | Selects + develops control activities              | RBAC permission catalog with ~100 keys (`docs/RBAC.md`); rate limiting per module    | `app/core/permissions.py`, `app/core/rate_limit.py`           |
| CC5.2 | Selects + develops general IT controls             | Multi-tenancy auto-filter; encryption at rest (Fernet + BYOK); TLS in transit       | `app/core/tenant_orm.py`, `app/core/encryption.py`            |
| CC5.3 | Deploys through policies and procedures            | CONTRIBUTING.md + branch protection + CODEOWNERS + required CI checks               | Files at repo root + GitHub config                            |

## CC6 — Logical & Physical Access (most relevant for a SaaS)

### CC6.1 — Authentication

| ID | Control                                              | EnterpriseCore implementation                                                       | Evidence                                                     |
|----|------------------------------------------------------|-------------------------------------------------------------------------------------|--------------------------------------------------------------|
| CC6.1a | Password complexity + storage                       | bcrypt with `passlib`, password_min_length config, no plaintext storage             | `app/core/security.py::hash_password`                        |
| CC6.1b | MFA                                                 | TOTP MFA via `pyotp` (`/auth/mfa/*`)                                                | `app/core/mfa.py`, `tests/test_mfa.py`                       |
| CC6.1c | SSO (Phase 6)                                       | OIDC + SAML SSO with IdP-initiated and SP-initiated flows                           | `app/api/v1/endpoints/sso.py`, migration 0014                |
| CC6.1d | Session management                                  | Short-lived JWT access tokens (15m) + refresh-rotation; httpOnly + `__Host-` cookies | `app/core/security.py::create_access_token`, `auth.py`       |
| CC6.1e | Account lockout                                     | Rate limiting per IP + per username on `/auth/login`                                | `app/core/rate_limit.py`                                     |
| CC6.1f | Failed-login monitoring                             | `LoginAttempt` model + `/security/login-attempts` endpoint                          | `app/models/security.py`                                     |

### CC6.2 — Authorization

| ID | Control                                              | EnterpriseCore implementation                                                       | Evidence                                                     |
|----|------------------------------------------------------|-------------------------------------------------------------------------------------|--------------------------------------------------------------|
| CC6.2a | Role-based access                                   | 8 built-in roles + custom roles + ~100-key permission catalog (`docs/RBAC.md`)       | `app/core/permissions.py`, migration 0017                    |
| CC6.2b | Least privilege                                     | Built-in role mapping grants only the reads/writes each role needs; admins can carve more granular custom roles | `BUILT_IN_ROLE_PERMISSIONS`                                  |
| CC6.2c | Authorization changes audited                       | Every role/permission change writes to `audit_logs` with action `rbac.*`             | `audit_logs` table                                           |
| CC6.2d | Periodic access review                              | `GET /api/v1/rbac/users/{user_id}/effective-permissions` exposes the resolved set    | RBAC endpoint                                                |

### CC6.3 — User lifecycle

| ID | Control                                              | EnterpriseCore implementation                                                       | Evidence                                                     |
|----|------------------------------------------------------|-------------------------------------------------------------------------------------|--------------------------------------------------------------|
| CC6.3a | Invitation flow                                     | `POST /tenants/me/users/invite` issues a signed token; `accept-invite` consumes it  | `app/api/v1/endpoints/tenants.py`                            |
| CC6.3b | Provisioning via SCIM 2.0                           | SCIM provider endpoints under `/scim/v2/*`                                          | `app/api/v1/endpoints/scim.py`                               |
| CC6.3c | Termination                                         | `is_active=False` on the User row revokes all tokens; SCIM `replace` mirrors the change | `users.is_active`                                            |
| CC6.3d | GDPR erasure                                        | `POST /api/v1/gdpr/erasure` produces a tombstoned export and removes PII            | `app/api/v1/endpoints/gdpr.py`                               |

### CC6.6 — External access

| ID | Control                                              | EnterpriseCore implementation                                                       | Evidence                                                     |
|----|------------------------------------------------------|-------------------------------------------------------------------------------------|--------------------------------------------------------------|
| CC6.6a | IP allowlist                                        | Per-tenant CIDR allowlist enforced by `IPAllowlistMiddleware`                       | `app/core/ip_allowlist.py`, `tests/test_ip_allowlist.py`     |
| CC6.6b | Public surface explicitly enumerated                 | Public bypass list: `/api/health`, `/metrics`, `/widget.js`, `/site/*`, `/api/v1/auth/*`, `/scim/v2/*`, `/api/v1/webchat/public/*` | `app/core/ip_allowlist.py::_BYPASS_PREFIXES` |
| CC6.6c | Trusted proxy IP extraction                          | `X-Forwarded-For` leftmost honoured for real client IP                              | `app/core/ip_allowlist.py::_extract_client_ip`               |

### CC6.7 — Encryption at rest

| ID | Control                                              | EnterpriseCore implementation                                                       | Evidence                                                     |
|----|------------------------------------------------------|-------------------------------------------------------------------------------------|--------------------------------------------------------------|
| CC6.7a | Field-level encryption                              | Fernet-encrypted columns for vault passwords, MFA secrets, AI keys, audit-stream credentials | `app/core/security.py::encrypt_text`, `app/core/encryption.py::encrypt_field` |
| CC6.7b | Per-tenant DEK                                       | `TenantEncryptionKey` row per tenant with envelope encryption                       | `app/models/security_hardening.py`                           |
| CC6.7c | BYOK with customer-managed KMS                       | AWS KMS, GCP KMS, Azure Key Vault, HashiCorp Vault Transit (`docs/BYOK.md`)         | `app/core/kms/`                                              |
| CC6.7d | Key rotation                                         | `POST /api/v1/encryption/rotate`; old-version ciphertext still readable             | `rotate_tenant_dek`                                          |
| CC6.7e | DB-level encryption                                  | Recommended PostgreSQL `pgcrypto` / TDE at the cloud-provider layer                 | `docs/CLOUD_DEPLOYMENT.md`                                   |
| CC6.7f | Backups encrypted                                    | Backups carry the same DEK protection; archive files written to encrypted storage   | `app/services/backups.py`                                    |

### CC6.8 — Encryption in transit

| ID | Control                                              | EnterpriseCore implementation                                                       | Evidence                                                     |
|----|------------------------------------------------------|-------------------------------------------------------------------------------------|--------------------------------------------------------------|
| CC6.8a | TLS for all public endpoints                        | Terminated at the load balancer; documented in `docs/CLOUD_DEPLOYMENT.md`           | Deployment guide                                             |
| CC6.8b | HSTS enabled                                         | `SecurityHeadersMiddleware` sets `Strict-Transport-Security: max-age=31536000`      | `app/core/security_headers.py`                               |
| CC6.8c | TLS 1.2+ only                                        | Documented LB configuration in deployment guide                                     | `docs/CLOUD_DEPLOYMENT.md`                                   |

## CC7 — System Operations

| ID | Control                                              | EnterpriseCore implementation                                                       | Evidence                                                     |
|----|------------------------------------------------------|-------------------------------------------------------------------------------------|--------------------------------------------------------------|
| CC7.1 | Detects misconfigurations + vulnerabilities          | Dependency audit via `pip-audit`; license check in CI; static analysis via ruff     | CI workflow                                                  |
| CC7.2 | Logging + monitoring                                 | Structured logs via loguru; Prometheus metrics; OTel traces; per-request request_id | `app/core/logging.py`, `app/core/observability.py`           |
| CC7.3 | Incidents detected, evaluated, communicated          | Audit-stream destinations push to SIEM; Sentry catches uncaught errors              | `app/services/audit_streamer.py`, `app/core/sentry.py`        |
| CC7.4 | Incident response                                    | Runbook in `docs/RELEASE_PROCESS.md`; on-call rotation customer-side                | Doc                                                          |
| CC7.5 | Recovery activities                                  | Documented restore path + backup retention                                          | `docs/SELF_HOSTING.md`                                       |

## CC8 — Change Management

| ID | Control                                              | EnterpriseCore implementation                                                       | Evidence                                                     |
|----|------------------------------------------------------|-------------------------------------------------------------------------------------|--------------------------------------------------------------|
| CC8.1 | Authorizes changes                                   | Pull request review required; CODEOWNERS                                            | GitHub config                                                |
| CC8.2 | Designs + develops + acquires changes                | Test-first; 535+ pytest cases; Playwright E2E suite                                 | `tests/`, `e2e/`                                             |
| CC8.3 | Implements changes                                   | Idempotent Alembic migrations; staged rollouts via Electron auto-updater + feature flags | `alembic/versions/`, `docs/AUTO_UPDATE.md`                   |
| CC8.4 | Tracks changes                                       | `audit_logs` for runtime changes; git history for code; release notes per version    | `audit_logs`, `CHANGELOG.md`                                 |

## CC9 — Risk Mitigation

| ID | Control                                              | EnterpriseCore implementation                                                       | Evidence                                                     |
|----|------------------------------------------------------|-------------------------------------------------------------------------------------|--------------------------------------------------------------|
| CC9.1 | Identifies + selects risk responses                  | Threat model in `SECURITY.md`; mitigations tracked in roadmap                       | Doc                                                          |
| CC9.2 | Manages vendor + business partner risks              | Dependency policy in `requirements*.txt`; SBOM generation in CI                     | CI workflow                                                  |

---

## Availability (A1)

| ID | Control                                              | EnterpriseCore implementation                                                       | Evidence                                                     |
|----|------------------------------------------------------|-------------------------------------------------------------------------------------|--------------------------------------------------------------|
| A1.1 | Capacity planning                                    | Prometheus dashboards on CPU/memory/DB connections                                  | Grafana dashboards in `ops/`                                 |
| A1.2 | Environmental protections, backups, recovery         | Daily backups via `BackupSchedule`; offsite copies; quarterly restore drills        | `app/models/security.py::BackupSchedule`                     |
| A1.3 | Tests recovery plan                                  | DR runbook in `docs/SELF_HOSTING.md`                                                | Doc                                                          |

## Confidentiality (C1)

| ID | Control                                              | EnterpriseCore implementation                                                       | Evidence                                                     |
|----|------------------------------------------------------|-------------------------------------------------------------------------------------|--------------------------------------------------------------|
| C1.1 | Identifies confidential information                  | Permissions catalog tagged at category level; PII columns enumerated in this doc    | `docs/RBAC.md`, this doc                                     |
| C1.2 | Disposes of confidential information                 | GDPR erasure endpoint with cryptographic tombstoning of the tenant DEK              | `app/api/v1/endpoints/gdpr.py`                               |

---

## Evidence-collection cheat sheet

| Need to prove…                          | Pull this                                                                                  |
|-----------------------------------------|---------------------------------------------------------------------------------------------|
| RBAC is enforced                        | `tests/test_rbac.py` results; `effective_permissions` output for a sample user             |
| Encryption at rest                      | `tenant_encryption_keys` row count + `kms_provider`; `tests/test_encryption_byok.py`        |
| IP allowlist is enforced                | `TenantSecurityPolicy` row + `tests/test_ip_allowlist.py`                                  |
| Audit logs reach the SIEM               | `AuditStreamDestination` rows with non-null `last_success_at`; SIEM-side ingest record      |
| MFA is enrolled                         | `users.mfa_enabled` count vs total active users                                            |
| Session timeout                         | `access_token_ttl_minutes` config + JWT decode                                             |
| Failed-login monitoring                 | `login_attempts` rows                                                                       |
| Tenant isolation                        | `tests/test_tenant_isolation.py` results                                                    |
| Change control                          | GitHub PR review history + CHANGELOG                                                        |

Auditors should request screen recordings of `GET /api/v1/encryption/key`,
`GET /api/v1/rbac/users/{u}/effective-permissions`, and a sample SIEM
ingest log from the audit-stream destination for the in-scope tenant.
