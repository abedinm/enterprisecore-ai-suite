# PIPA Compliance Mapping (South Korea Personal Information Protection Act)

The Personal Information Protection Act (PIPA, 개인정보 보호법) is South Korea's comprehensive privacy law, materially amended in March 2023 (effective 15 September 2023) which unified the regime previously split with the Network Act. PIPA is enforced by the **Personal Information Protection Commission (PIPC, 개인정보보호위원회)**.

PIPA is among the strictest privacy regimes in the world: it prescribes specific consent forms, retention durations, and notice content with little room for interpretation. Penalties include criminal sanctions for officers.

---

## Roles

- **Personal Information Controller (개인정보처리자)** — the customer operating the tenant.
- **Personal Information Processor (수탁자)** — EnterpriseCore when run as a service.
- **Data Subject (정보주체)** — the natural person.
- **Privacy Officer (개인정보 보호책임자, CPO)** — must be designated by every Controller.

---

## Article 15 — Collection and Use

PI may be collected and used only with: consent, statutory requirement, contract performance with subject, urgent need to protect life/body/property, performance of public-body function, legitimate interest of the Controller balanced against subject's rights, public-interest-broadcast / academic-research with safeguards.

**EnterpriseCore feature:** `lawful_basis` audit dimension supports each PIPA ground. The default is consent.

---

## Article 16 — Limitation on Collection

Collection must be minimal. The Controller must not refuse service for declining to consent to optional items.

**EnterpriseCore feature:**
- Field collection toggles let customers turn off optional columns.
- The signup form renders mandatory vs. optional consent items separately. Declining optional items does not block account creation.

---

## Article 17 — Provision to Third Parties

Requires subject's prior, separate consent (unless statutory exception). The Controller must inform the subject of: recipient, purpose, items, retention by recipient, and the right to refuse.

**EnterpriseCore feature:** Third-party provision register + separate consent toggle per recipient. The integrations module captures recipient identity on connect.

---

## Article 18 — Use and Provision Beyond Specified Purpose

Prohibited unless: separate consent obtained, statutory exception, life/body protection, or pseudonymised for statistical / academic / public-interest research.

---

## Article 21 — Destruction

PI must be destroyed without delay when retention purpose is achieved or retention period expires.

**EnterpriseCore feature:** Retention rules with auto-deletion job. The default retention is the shortest of: consent duration, statutory retention floor, or 3 years inactive.

---

## Article 22 — Consent

Consent must distinguish mandatory items from optional items. Each purpose requires separate consent. The Controller must use a "method enabling the subject to clearly recognise" the consent (e.g., bold heading, separate page).

**EnterpriseCore feature:**
- Consent UI separates mandatory and optional with distinct visual treatment.
- Each purpose has its own toggle.
- Bundled consent is impossible at the API level — `POST /api/v1/gdpr/consent` accepts a single purpose at a time.

---

## Article 23 — Sensitive Information

Ideology, beliefs, union membership, political opinion, health, sexual life, genetic information, criminal record, biometric data for identification.

Requires explicit separate consent OR statutory requirement.

**EnterpriseCore feature:** Sensitive field classification + role-gated access, same as PIPL / LGPD / GDPR Art 9.

---

## Article 24 — Unique Identifiers (Resident Registration Number)

The Korean Resident Registration Number (주민등록번호, RRN) has the strictest handling rules: collection is prohibited unless specifically authorised by another statute (Real Name Financial Transactions Act, etc.). Encryption is mandatory.

**EnterpriseCore feature:**
- The default `User` model does not include an RRN column.
- For tenants requiring RRN handling (e.g., Korean financial-services customers), the optional `kr_rrn` field can be enabled via a migration; when enabled, the field is column-level encrypted using a tenant-specific KMS key, and access is gated behind the `rrn:read` permission.

---

## Article 25 — Visual Information Processing Devices

CCTV-specific provisions. Not directly applicable to EnterpriseCore deployments but mentioned for completeness.

---

## Article 26 — Outsourcing

When outsourcing PI handling, the Controller must:
- Document the outsourcing in writing
- Disclose the trustee's identity and outsourced work
- Supervise the trustee

**EnterpriseCore feature:** When self-hosted by the customer, EnterpriseCore is not a separate trustee. When run by a managed-service provider, the standard PIPA-DPA at `docs/compliance/dpa-template-pipa.md` covers Article 26 requirements.

---

## Article 28-2 — Pseudonymised Information

The 2020 amendment introduced pseudonymisation. Pseudonymised data can be processed for statistical, scientific research, and archival public-interest purposes without subject consent, subject to safeguards.

**EnterpriseCore feature:** Same pseudonymisation tooling as APPI.

---

## Articles 28-8 to 28-11 — Cross-Border Transfer (post-2023 amendment)

Cross-border transfer of PI is permitted when:
1. The subject has given separate consent after receiving destination-country information;
2. The destination is on the PIPC's adequacy list;
3. The destination has obtained PIPC certification;
4. Specific safeguards (binding instruments approved by PIPC) are in place;
5. Or one of the narrow exceptions applies.

The Controller must publish a cross-border transfer policy.

**EnterpriseCore feature:**
- Cross-border register and destination dossiers (same pattern as APPI).
- Cross-border transfer policy template at `documents/pipa/cross-border-policy.md`.
- `DATA_RESIDENCY_REGION=kr` enforces single-region storage for KR-residency tenants.

---

## Articles 35 to 37 — Subject Rights

| Right | Article | Endpoint |
|---|---|---|
| Notification of source / purpose / recipient | 20 | privacy notice + acquisition notice |
| Access | 35 | `GET /api/v1/gdpr/data-subject/export` |
| Correction / deletion | 36 | `PATCH` / `DELETE /api/v1/gdpr/data-subject` |
| Suspension of processing | 37 | `POST /api/v1/gdpr/data-subject/pause` |

SLA: 10 days per Article 35 §3 (extendable by 10 days with notice).

---

## Article 29 — Safety Measures

Technical, administrative, and physical safeguards. The PIPC has issued a detailed Standard for Safe Personal Information Management:
- Internal management plan
- Access control
- Access logs (1-year retention; 3 years for processing >50 000 subjects)
- Encryption of unique identifiers and passwords
- Anti-virus / anti-intrusion
- Physical safeguards

EnterpriseCore satisfies these via the security baseline (encryption, RBAC, audit streaming, IP allowlist) plus log retention configurable up to PIPA's 3-year requirement.

---

## Article 31 — Privacy Officer

Every Controller must designate a Privacy Officer (CPO). The CPO oversees PI handling, processes subject complaints, and runs internal audit.

**EnterpriseCore feature:** Tenant Settings → Compliance → Privacy Officer captures name, title, contact. The privacy notice renders this publicly.

---

## Article 34 — Breach Notification

The Controller must notify affected subjects and the PIPC of a breach involving leakage. The 2023 amendment tightened the timing:
- Notification to subjects: "without delay" (PIPC guidance: 72 hours).
- Notification to PIPC: when the breach involves >1 000 subjects.

**EnterpriseCore feature:** Standard breach playbook + Korean-specific addendum in `docs/INCIDENT_RESPONSE.md`.

---

## Article 39 — Damages

Subjects can claim damages; the Act provides a statutory minimum and shifts the burden to the Controller to prove no fault.

---

## Records to Maintain

| Record | Location | Retention |
|---|---|---|
| Consent records (separated by purpose, mandatory vs optional) | `consent_records` | Life + 5 years |
| Outsourcing documents | `documents/pipa/outsourcing-*` | Life + 5 years |
| Third-party provision log | `third_party_provisions` | Life + 5 years |
| Cross-border transfer policy | `documents/pipa/cross-border-policy.md` | Permanent |
| Privacy Officer designation | `compliance_attestations` | Permanent |
| Access logs | Configured sink | 1 year (≤50k subjects) / 3 years (>50k) |
| Breach register | `breach_notices` | 5 years |

---

## Audit Checklist

- [ ] Privacy Officer designated and contact public
- [ ] Mandatory / optional consent separation verified in UI
- [ ] Sensitive PI controls verified
- [ ] RRN handling DISABLED unless legally required; if enabled, encryption verified
- [ ] Cross-border transfer policy published; destination dossiers current
- [ ] Subject rights endpoints reachable; 10-day SLA achievable
- [ ] Outsourcing documents on file for all trustees
- [ ] Access logs retained per Article 29 floor
- [ ] Breach playbook updated with PIPC contact and 72-hour timeline
- [ ] Annual internal audit completed by CPO
