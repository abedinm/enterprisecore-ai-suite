# APPI Compliance Mapping (Japan Act on the Protection of Personal Information)

The Act on the Protection of Personal Information (APPI, 個人情報の保護に関する法律) is Japan's principal privacy law, materially amended in 2020 (effective April 2022) and again in 2023. It is enforced by the **Personal Information Protection Commission (PPC, 個人情報保護委員会)**.

The 2022 amendments brought APPI closer to GDPR by introducing data-subject rights, breach notification, and tightened cross-border transfer rules.

---

## Roles

- **Personal Information Handling Business Operator (PIHBO, 個人情報取扱事業者)** — any entity using a personal-information database for business. Customers operating EnterpriseCore tenants are PIHBOs.
- **Person Identified by Personal Information** (the data subject).
- **Trustee** (受託者) — analogous to a Processor. EnterpriseCore when run as a service.

---

## Article 17 — Specification of Use Purpose

The PIHBO must specify the purpose of use as much as possible.

**EnterpriseCore feature:** Every processing activity in `processing_activities` has an explicit purpose statement. Activities for which no purpose is recorded are blocked from running personal-data jobs.

---

## Article 18 — Restriction on Use

PI must not be used beyond the necessary scope of the specified purpose without the subject's consent.

**EnterpriseCore feature:** New feature flags that broaden the use of existing PI require an admin to acknowledge a "scope expansion" prompt that triggers a consent refresh queue.

---

## Article 19 — Proper Acquisition

PI must not be acquired by deceit or other improper means.

**EnterpriseCore feature:** Notice-and-consent UI is enforced at all PI capture points. Field-level audit annotates the source (subject / third party / public source).

---

## Article 20 — Notice of Use Purpose at Acquisition

The PIHBO must promptly notify or publicly announce the purpose of use after acquiring PI.

**EnterpriseCore feature:** Privacy notice template `documents/privacy_notice/template-appi.md`. The signup flow renders the notice in Japanese for `locale=ja-JP` tenants.

---

## Article 21 — Accuracy

The PIHBO must endeavour to keep PI accurate and up to date within the necessary scope.

**EnterpriseCore feature:** Subject correction endpoint + stale-record reporting (same as POPIA Condition 5).

---

## Article 23 — Security Management Measures

The PIHBO must take necessary and appropriate action for the security management of PI. PPC guidelines elaborate four categories of measures: organisational, human, physical, technical.

EnterpriseCore controls:
- **Organisational:** RBAC, role review checklist, incident playbook.
- **Human:** training acknowledgements tracked in `compliance_attestations`.
- **Physical:** delegated to the underlying cloud / on-prem provider; covered in deployment runbooks.
- **Technical:** AES-256 at rest, TLS 1.2+, audit streaming, IP allowlist, anomaly detection.

**Evidence:** SOC2 controls register in `docs/SOC2_CONTROLS.md` maps to PPC's security management taxonomy.

---

## Article 25 — Supervision of Trustees

When entrusting handling to a third party, the PIHBO must exercise necessary and appropriate supervision.

**EnterpriseCore feature:** When EnterpriseCore is run by a third party for the customer (rather than self-hosted), the standard DPA at `docs/compliance/dpa-template-appi.md` covers PPC supervision criteria. Sub-processors are listed in `docs/SUBPROCESSORS.md` (created on demand if missing).

---

## Article 26 — Breach Notification

The 2022 amendments mandate notification to the PPC AND affected individuals where a breach is "likely to cause damage to the rights or interests of individuals." The deadline is "promptly" — PPC guidance: 3-5 days for preliminary report, 30 days for final.

**EnterpriseCore feature:** Breach detection via audit-stream anomaly rules, notification queue, PPC report template in `docs/INCIDENT_RESPONSE.md` (Japan section).

---

## Article 27 — Restriction on Third-Party Provision

Provision of PI to a third party requires the subject's prior consent, except for: legal obligation, vital interest, public-health/child-welfare, public-body cooperation.

**Opt-out provision:** PI can be provided to third parties on an opt-out basis if notified to the PPC and made readily available to subjects, **but** the opt-out route is unavailable for sensitive PI, illegally acquired PI, or PI of subjects who have opted out.

**EnterpriseCore feature:**
- Third-party share register at `third_party_provisions` table.
- Consent capture flow forces explicit (not opt-out) consent for sensitive PI.
- PPC opt-out filing template at `documents/appi/opt-out-filing.md`.

---

## Article 28 — Cross-Border Transfer

Provision of PI to a third party in a foreign country requires the subject's consent UNLESS:
- The country has been recognised by the PPC as providing equivalent protection (currently the EU and UK).
- The recipient has implemented measures equivalent to APPI (the PIHBO supervises).

Even when consent is obtained, the PIHBO must provide the subject with reference information about the destination country (data protection regime, recipient's measures).

**EnterpriseCore feature:**
- Cross-border register at `cross_border_transfer_register`.
- Destination-country dossier template at `documents/appi/destination-dossier-{country}.md`.
- Consent flow surfaces the destination-country summary when the recipient is outside Japan / EU / UK.

---

## Articles 32 to 39 — Subject Rights (introduced/expanded in 2022)

| Right | Article | Endpoint |
|---|---|---|
| Disclosure of retained PI | 33 | `GET /api/v1/gdpr/data-subject/export` |
| Correction, addition, deletion | 34 | `PATCH /api/v1/gdpr/data-subject` |
| Cessation of use / deletion | 35 | `DELETE /api/v1/gdpr/data-subject` |
| Cessation of third-party provision | 35 | `POST /api/v1/gdpr/data-subject/halt-third-party` |
| Disclosure of third-party provision records | 33-2 | `GET /api/v1/gdpr/data-subject/third-party-log` |
| Receive in electronic format | 33 | `?format=json` query param |

APPI does not stipulate a SLA but PPC practice expects "without delay" — industry standard is 30 days.

---

## Article 16 — Sensitive PI (要配慮個人情報)

Race, creed, social status, medical history, criminal record, fact of having been a victim of crime, and similar categories.

Sensitive PI cannot be acquired without the subject's prior consent (with limited exceptions) and cannot be provided to third parties on the opt-out basis.

**EnterpriseCore feature:** Same `sensitive` field classification + role-gated access + bulk-export refusal as the other jurisdictions.

---

## Article 16-2 — Pseudonymised Information (仮名加工情報)

The 2022 amendment introduced "pseudonymised information" — PI processed so identification is not possible without combining with other information. Loosens some restrictions (no subject-rights obligations) but adds: cannot be provided to third parties, cannot be combined with other info to re-identify.

**EnterpriseCore feature:** The `tenant_export.sh` script (see `scripts/backup/`) supports a `--pseudonymise` mode that hashes direct identifiers with a tenant-specific salt before export, producing an APPI-compliant pseudonymised dataset.

---

## Article 16-3 — Anonymously Processed Information (匿名加工情報)

Processed so subjects cannot be identified and the PI cannot be restored. APPI imposes specific minimum standards for the de-identification technique.

**EnterpriseCore feature:** Documentation in `docs/PERFORMANCE.md` references the anonymisation procedure used for benchmark datasets, which conforms to PPC's standard.

---

## Records to Maintain

| Record | Location | Retention |
|---|---|---|
| Use-purpose registry | `processing_activities` | Life of activity |
| Consent records | `consent_records` | Life + 3 years |
| Third-party provision log | `third_party_provisions` | 3 years (APPI Article 29) |
| Receipt log for incoming PI from third parties | `third_party_acquisitions` | 3 years (APPI Article 30) |
| Breach register | `breach_notices` | 5 years |
| Cross-border destination dossiers | `documents/appi/destination-*` | Life of transfer + 3 years |

---

## Audit Checklist

- [ ] Use purposes specified for every processing activity
- [ ] Privacy notice published in Japanese
- [ ] Sensitive PI flagged and access-controlled
- [ ] Third-party provision log + receipt log maintained
- [ ] Opt-out filing on record with the PPC (if used)
- [ ] Cross-border transfer dossiers current
- [ ] Breach response timeline verified by tabletop within last 12 months
- [ ] Subject-rights endpoints reachable and tested
- [ ] Trustee supervision DPAs signed for any sub-processor
- [ ] Backup encryption and offsite copy verified
