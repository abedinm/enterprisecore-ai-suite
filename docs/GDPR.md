# GDPR data export + erasure

EnterpriseCore implements the two main GDPR data-subject rights — Right
to Access (Art. 15) via data export, and Right to Erasure (Art. 17) via
anonymization. This document covers what we export, what gets anonymized,
what we retain for legal reasons, and how to wire the endpoints into your
privacy workflow.

## Data categories we store

`GET /api/v1/gdpr/data-categories` is the live, machine-readable source
of truth — link your privacy page at it so it can never drift. The
categories are:

| Category                            | What's in it                                                 | Retention                                          |
| ----------------------------------- | ------------------------------------------------------------ | -------------------------------------------------- |
| **Account**                         | email, full_name, avatar_url, department, locale, theme      | Until account closure + 30 days, then anonymized   |
| **Authentication**                  | password_hash (bcrypt), MFA secret (Fernet-encrypted), refresh tokens | Until logout/rotation; cleared on erasure |
| **Activity & audit**                | audit logs, search history, login attempts                   | 7 years for legal compliance; user id anonymized on erasure |
| **Business records authored by you**| CRM leads/deals, invoices, projects, tasks, etc.             | Indefinitely — tied to the tenant, not the individual |
| **AI usage**                        | conversations, messages, token usage / spend                 | 13 months for billing reconciliation, then aggregated |
| **Webchat**                         | conversation + message rows                                  | 12 months unless linked to a CRM contact           |

## Right to Access — data export

Any user can export their own data. Admins can export any user in the
same tenant. Cross-tenant export is blocked by the multi-tenant
auto-filter.

```http
POST /api/v1/gdpr/export
Authorization: Bearer <jwt>
Content-Type: application/json

{}                          # export the caller
{"user_id": "01HVK..."}     # export another user (admin only)
```

The job runs synchronously and the response carries `status: "ready"`
plus a signed `download_url` valid for 24 hours:

```json
{
  "id": "01HVK...",
  "user_id": "01HVK...",
  "status": "ready",
  "download_url": "/api/v1/gdpr/export/01HVK.../download?token=...",
  "expires_at": "2026-05-24T10:42:31+00:00",
  "record_count": 412
}
```

GET the URL to retrieve the JSON bundle. The token is single-purpose:
deleting the job row invalidates it, and re-exporting issues a new one.

### Bundle structure

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-23T10:42:31.123456+00:00",
  "user_id": "01HVK...",
  "tenant_id": "01HVK...",
  "profile": { "email": "...", "full_name": "...", "password_hash": "<redacted>", ... },
  "records_by_table": {
    "leads": [ ... ],
    "deals": [ ... ],
    "invoices": [ ... ],
    "ai_usage_records": [ ... ],
    "audit_logs": [ ... ]
  },
  "data_categories": [...],
  "record_count": 412
}
```

`password_hash` and `mfa_secret` are always redacted before serialisation
— the export gives the user a copy of their data, never the keys an
attacker could use to impersonate them.

### Polling

Although the current implementation completes synchronously, the
`GET /api/v1/gdpr/export/{job_id}` endpoint exists for a future async
queue migration. Callers should treat the export as eventually-completing
and poll until `status == "ready"`.

## Right to Erasure — anonymization

Hard-deleting a user row would break dozens of `created_by_id` /
`actor_id` FKs across the suite — audit logs, invoices, project tasks,
etc. — and would itself violate the 7-year legal-retention requirement on
audit records.

We therefore **anonymize** the user row in place. Specifically:

1. `email` → `erased-<sha256-fingerprint>@deleted.invalid`
2. `full_name` → `<deleted>`
3. `avatar_url`, `department` → `null`
4. `mfa_secret`, `mfa_enabled` → cleared
5. `password_hash` → re-bcrypted from random bytes (login becomes impossible)
6. `is_active` → `false`
7. All refresh tokens for the user → `revoked_at = now()`

Then we write a `GdprErasureReceipt` row recording who requested it, when,
the reason, and which fields were cleared. The receipt is kept
indefinitely as proof of compliance.

```http
POST /api/v1/gdpr/erasure-request           (admin only)
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "user_id": "01HVK...",
  "reason": "Subject access request received 2026-05-22"
}
```

Returned: the full receipt row including `fields_cleared`,
`records_anonymized`, and `completed_at`.

Self-erasure is blocked — an admin must hand off the role before erasing
their own account, so the tenant doesn't get orphaned without an admin.

## Receipts (proof of compliance)

`GET /api/v1/gdpr/erasure-receipts` (admin only) returns every receipt
ever recorded for the current tenant, newest first. Use this when a
regulator or auditor asks "how do I know you actually honoured the
erasure?" — point them at the row.

## What's retained even after erasure

| Retained                            | Why                                                       |
| ----------------------------------- | --------------------------------------------------------- |
| Audit log rows referencing the user | GDPR Art. 17(3)(e) — public-interest / legal-claim exception. Rows now reference an anonymized id with no PII attached. |
| Invoices, contracts, financial records they touched | Legal obligation under tax law (typically 7 years). |
| Business content (leads, deals, tasks they created) | Belongs to the tenant, not the individual. The author attribution is now the anonymized user id, with no PII. |
| Erasure receipt itself              | Proof of compliance.                                       |

## DPA templates

Standard DPA / SCC references your legal team will want:

- EU SCC 2021/914 — Module 2 (controller-to-processor) when EnterpriseCore
  is processing data on the customer's behalf.
- UK IDTA / addendum if any of your subjects are UK residents.
- Article 28 GDPR processor agreement clauses.

If you need a pre-flight DPA aligned to our actual processing flow,
contact `privacy@enterprisecore.app`.

## Internals

- Code: `app/services/gdpr.py` (build + erase) + `app/api/v1/endpoints/gdpr.py`
- Models: `GdprExportJob`, `GdprErasureReceipt` in `app/models/webhooks.py`
- Tests: `tests/test_gdpr.py`
- Storage: export files live under `storage/exports/<job_id>.json`. Stale
  files are removed by the housekeeping job on the 24h expiry boundary.

Erasure also fires a `user.deactivated` event so any external system you
sync against (CRM, HRIS, billing) can take action on its end too.
