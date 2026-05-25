# DPDP Compliance Mapping (India Digital Personal Data Protection Act, 2023)

EnterpriseCore deployments serving Data Principals located in India must comply with the Digital Personal Data Protection Act 2023 (DPDP). This document maps each statutory obligation to the EnterpriseCore feature, customer configuration step, or evidence pointer that satisfies it.

The DPDP applies to processing of digital personal data within India, and to processing outside India where the activity is in connection with offering goods or services to Data Principals in India.

---

## Roles

- **Data Fiduciary** — the customer operating an EnterpriseCore tenant for their own users.
- **Data Processor** — Anthropic-style entity that processes on the Fiduciary's behalf. EnterpriseCore acts as a Processor when self-hosted by the customer.
- **Data Principal** — the end user whose personal data is processed (employees, customers, contacts in CRM, etc.).
- **Significant Data Fiduciary** (SDF) — designated by the Central Government based on volume/sensitivity. SDFs have extra duties (DPO, DPIA, audit).

---

## Section 4 — Grounds for Processing

DPDP recognises two grounds: (a) consent, and (b) certain "legitimate uses" (employment, legal compliance, court order, breach response, medical emergency, public interest).

**EnterpriseCore feature:** Consent is captured at signup via the DPA acceptance flow (`POST /api/v1/tenants/signup` records `dpa_accepted_at`). Each tenant can record additional Data Principal consents through the GDPR module (`POST /api/v1/gdpr/consent`), which the DPDP module reuses verbatim — the underlying `consent_records` table includes `purpose`, `granted_at`, `withdrawn_at`, and `evidence` columns.

**Customer action:** Configure the purpose-string library under Tenant Settings → Privacy → Purposes before collecting personal data.

**Evidence:** `backend/tests/test_gdpr.py::test_consent_record_lifecycle`.

---

## Section 5 — Notice

Before or at the time of consent the Fiduciary must give a notice covering: personal data being processed, purpose, manner of exercising rights, and complaint mechanism.

**EnterpriseCore feature:** The signup and consent endpoints accept a `notice_id` referencing a versioned privacy notice stored in `documents/privacy_notice/*.md`. The notice version is captured alongside each consent record so a later notice update cannot retroactively change what the Data Principal agreed to.

**Customer action:** Upload your DPDP-compliant notice as `documents/privacy_notice/v1-dpdp.md` and link it during signup.

---

## Section 6 — Consent

Consent must be free, specific, informed, unconditional, unambiguous, and signified by clear affirmative action. The Data Principal can withdraw at any time, and withdrawal must be as easy as giving consent.

**EnterpriseCore feature:**
- Consent records are immutable — a withdrawal creates a new row, not an update — so the audit trail shows when consent was given and revoked.
- Withdrawal is exposed at `DELETE /api/v1/gdpr/consent/{consent_id}` and surfaces in the end-user privacy dashboard.
- Auto-tick / pre-ticked consent boxes are disabled in the React signup component — the consent toggle defaults to off.

**Evidence:** `frontend/src/components/Signup.tsx` consent toggle; `backend/tests/test_gdpr.py::test_consent_withdrawal_creates_new_record`.

---

## Section 7 — Legitimate Uses

For employment-related processing, EnterpriseCore's HR module sets `lawful_basis="legitimate_use_employment"` on employee records. No additional consent is captured for processing strictly necessary for the employment relationship.

---

## Section 8 — General Obligations of Data Fiduciary

Fiduciaries must:
- Ensure accuracy and completeness of data — supported by the data subject correction endpoint `PATCH /api/v1/gdpr/data-subject`.
- Implement reasonable security safeguards — see Section 32 mapping below.
- Notify the Data Protection Board of personal data breaches — see Section 33.
- Erase data when consent is withdrawn or the purpose is fulfilled — see Section 17.

**Customer action:** Configure retention rules under Tenant Settings → Privacy → Retention. Default retention is 7 years for financial records (Indian tax law) and 3 years for HR records.

---

## Section 12 — Rights of Data Principal

The DPDP grants five rights: access, correction, erasure, grievance redressal, and nomination.

| Right | Endpoint | Customer SLA |
|---|---|---|
| Access | `GET /api/v1/gdpr/data-subject/export` | 30 days |
| Correction | `PATCH /api/v1/gdpr/data-subject` | 30 days |
| Erasure | `DELETE /api/v1/gdpr/data-subject` (soft delete + crypto-shred) | 30 days |
| Grievance | `POST /api/v1/gdpr/grievance` (routes to the configured DPO email) | 30 days |
| Nomination | `POST /api/v1/gdpr/nomination` | n/a (record only) |

**Evidence:** `docs/GDPR.md` data-subject section; `backend/tests/test_gdpr.py`.

---

## Section 17 — Erasure

On withdrawal of consent or fulfilment of purpose, personal data must be erased unless retention is required by law.

**EnterpriseCore feature:** The GDPR erasure endpoint performs a two-stage delete:
1. Immediate soft delete (the user can no longer authenticate, all PII fields are nulled).
2. After the retention window passes, a background job crypto-shreds the encryption key for that subject's blob storage, rendering files unrecoverable.

Financial records subject to mandatory retention (Indian Income Tax Act §44AA: 6 years) are masked rather than deleted — name and PAN are replaced with hashed tokens.

---

## Section 32 — Reasonable Security Safeguards

The Act requires "reasonable security safeguards to prevent personal data breach."

EnterpriseCore controls:
- AES-256 encryption at rest for the database (configurable; AWS RDS / Azure Postgres / GCP Cloud SQL all enabled by default in `deploy/terraform/`).
- TLS 1.2+ enforced via the SecurityHeadersMiddleware HSTS header (max-age=63072000, includeSubDomains, preload).
- RBAC with least-privilege roles — see `docs/RBAC.md`.
- IP allowlist per tenant — Tenant Settings → Security → Allowlist.
- Audit log streaming to SIEM (Splunk / Datadog / Sumo / generic webhook) — see `docs/INTEGRATIONS.md`.
- Quarterly secret rotation — `scripts/rotate_secrets.sh` (TODO: Wave 5).
- Pen-test schedule documented in `docs/SOC2_CONTROLS.md`.

**Evidence:** `backend/tests/test_security_headers.py`; `backend/tests/test_rate_limiting.py`; `backend/tests/test_tenant_isolation.py`.

---

## Section 33 — Breach Notification

A personal data breach must be notified to the Data Protection Board and to each affected Data Principal "in such form and manner as may be prescribed."

**EnterpriseCore feature:**
- Anomalous-access detection in the audit stream (see `audit-stream-backed-up.md` runbook).
- Pre-drafted notification templates in `docs/INCIDENT_RESPONSE.md`.
- The `POST /api/v1/admin/breach-notice` endpoint records the incident and, if configured, queues notification emails to all affected tenants.

**Customer action:** Configure the DPB contact and the Data Principal notification template under Tenant Settings → Compliance → Breach.

---

## Section 9 — Processing of Children's Data

Processing of personal data of children (under 18) requires verifiable parental consent. Tracking, behavioural monitoring, and targeted advertising directed at children are prohibited.

**EnterpriseCore feature:** The User model has a `date_of_birth` field. When set and the subject is under 18, the application:
- Rejects newsletter / marketing consent flags.
- Requires a `parent_consent_evidence` reference on the user record.
- Flags the tenant as needing children-data review on the admin dashboard.

**Customer action:** If your product is directed at children, set Tenant Settings → Privacy → Children = "yes" to enforce the above checks for all users in that tenant.

---

## Section 10 — Significant Data Fiduciary Obligations

SDFs must appoint a Data Protection Officer based in India, conduct DPIAs, and undergo periodic audits.

**EnterpriseCore feature:**
- DPO contact stored on the tenant — Tenant Settings → Compliance → DPO.
- DPIA template at `docs/compliance/dpia-template.md` (referenced by `docs/SOC2_CONTROLS.md`).
- Annual audit checklist auto-generated from the SOC2 controls register.

---

## Cross-border Transfer

Section 16 empowers the Central Government to notify countries to which personal data may not be transferred. The default position is permissive (transfers allowed unless restricted).

**EnterpriseCore feature:** Tenant data residency is configured at deployment time via the `DATA_RESIDENCY_REGION` env var. Self-hosted deployments are inherently single-region; multi-region deployments expose this as a tenant setting.

**Customer action:** Maintain a list of restricted countries (in your DPIA) and update IP allowlists / replication settings accordingly when the Government notifies new restrictions.

---

## Records to Maintain

| Record | Location | Retention |
|---|---|---|
| Consent records | `consent_records` table | Life of consent + 3 years |
| Notice versions | `documents/privacy_notice/` | Permanent |
| Breach register | `breach_notices` table | 6 years |
| DPIA outcomes | `documents/dpia/` | Life of processing + 3 years |
| Audit logs | Configured audit sink (Splunk / S3) | 1 year minimum |

---

## Audit Checklist

- [ ] DPA accepted at signup for every tenant
- [ ] Privacy notice uploaded and versioned
- [ ] DPO contact set for SDF tenants
- [ ] Retention rules configured
- [ ] Audit streaming target reachable (smoke test passes)
- [ ] IP allowlist reviewed quarterly
- [ ] Breach notification template customised
- [ ] Children-data flag set where applicable
- [ ] Backup encryption and offsite copy verified — see `scripts/backup/pg_backup.sh`
