# PDPA Compliance Mapping (Singapore Personal Data Protection Act 2012)

The Personal Data Protection Act 2012 (PDPA) governs the collection, use, and disclosure of personal data by organisations in Singapore. The 2020 amendments (effective 1 February 2021) introduced mandatory breach notification, enhanced consent frameworks, and a data portability right.

It is enforced by the **Personal Data Protection Commission (PDPC)**, with fines now up to 10% of annual Singapore turnover or SGD 1 million, whichever is higher.

---

## Roles

- **Organisation** — the customer operating the tenant.
- **Data Intermediary (DI)** — EnterpriseCore when run for the Organisation; subject to a subset of obligations.
- **Individual** — the data subject.
- **Data Protection Officer (DPO)** — every Organisation must appoint at least one DPO and publish their business contact (Section 11).

---

## Nine Obligations (PDPC framing)

PDPA is taught and audited through nine obligations. Mapping each:

### Obligation 1 — Consent

Sections 13–17. Consent is required unless deemed (continuation of an existing relationship) or under one of the exceptions in the First / Second Schedule (legitimate interest, business improvement, vital interest, etc., post-2020).

**EnterpriseCore feature:**
- Explicit consent at signup and per-purpose.
- Deemed-consent flag captured on imported records.
- Legitimate-interest assessment template at `documents/pdpa/lia-template.md`.

---

### Obligation 2 — Purpose Limitation

Section 18. Personal data may be collected/used/disclosed only for purposes a reasonable person would consider appropriate AND that the individual has been informed of.

**EnterpriseCore feature:** Processing activity registry + per-activity purpose statements.

---

### Obligation 3 — Notification

Section 20. The Organisation must notify the individual of the purposes on or before collection.

**EnterpriseCore feature:** Privacy notice rendered at signup; per-activity notice at first use.

---

### Obligation 4 — Access and Correction

Sections 21–22. Individuals can request access to their data and correction of inaccuracies.

| Right | Section | Endpoint |
|---|---|---|
| Access | 21 | `GET /api/v1/gdpr/data-subject/export` |
| Correction | 22 | `PATCH /api/v1/gdpr/data-subject` |

SLA: 30 days from request; fee allowed but must be reasonable.

---

### Obligation 5 — Accuracy

Section 23. Reasonable effort to ensure accuracy if the data will be used to make a decision affecting the individual OR disclosed to another organisation.

**EnterpriseCore feature:** Subject correction endpoint, stale-record reporting, dual-control workflow for high-impact decisions.

---

### Obligation 6 — Protection

Section 24. Reasonable security arrangements to prevent unauthorised access, collection, use, disclosure, copying, modification, or disposal.

EnterpriseCore controls match the global security baseline (encryption, RBAC, IP allowlist, audit streaming, backup encryption).

---

### Obligation 7 — Retention Limitation

Section 25. Cease retention or anonymise data when no longer needed for the purpose AND no longer needed for any legal/business reason.

**EnterpriseCore feature:** Retention rules per data category with auto-purge job.

---

### Obligation 8 — Transfer Limitation

Section 26. PI transferred outside Singapore must be at a standard of protection comparable to PDPA. Acceptable mechanisms: contractual clauses, binding corporate rules, certification (APEC CBPR / PRP).

**EnterpriseCore feature:**
- Cross-border register.
- Singapore SCC template at `documents/pdpa/scc-template.md`.
- `DATA_RESIDENCY_REGION=sg` enforces single-region storage for SG-residency tenants.

---

### Obligation 9 — Openness (and DPO)

Section 11–12. Organisation must develop and implement PDPA policies and practices; designate one or more DPOs; publish DPO business contact.

**EnterpriseCore feature:** Tenant Settings → Compliance → DPO captures name, role, email, phone. The privacy notice renders this publicly.

---

## Data Breach Notification (Sections 26A–26E, post-2020)

A "notifiable breach" is one that:
- (a) results in or is likely to result in significant harm to an affected individual, OR
- (b) is of a significant scale (PDPC threshold: ≥500 affected individuals).

Timing:
- Notify PDPC: as soon as practicable but no later than **3 calendar days** after assessment.
- Notify affected individuals: as soon as practicable on or after PDPC notification (unless an exception applies — remedial action taken, law-enforcement instruction, etc.).

**EnterpriseCore feature:** Breach detection, automated severity-and-scale assessment, PDPC notification template at `docs/INCIDENT_RESPONSE.md` (Singapore section).

---

## Data Portability (Section 26F, post-2020 — pending operationalisation)

The 2020 amendment introduced a portability right but its commencement is pending. Once operational, individuals can request that data be transmitted in a commonly-used machine-readable format to another organisation.

**EnterpriseCore feature:** `GET /api/v1/gdpr/data-subject/export?format=json|csv` already produces portable formats. The data-receiver flow will be added once the PDPC publishes the operational standard.

---

## Do Not Call (DNC) Provisions (Part IX-A)

Specific obligations for marketing messages — check the DNC Registry before sending Singapore-numbered SMS / call / fax.

**EnterpriseCore feature:** The marketing module's contact-list importer flags Singapore numbers and prompts the customer to confirm DNC clearance before scheduling.

---

## Records to Maintain

| Record | Location | Retention |
|---|---|---|
| DPO designation | `compliance_attestations` | Permanent |
| Consent records | `consent_records` | Life + 5 years |
| Cross-border transfer contracts | `documents/pdpa/scc-*` | Life of transfer + 5 years |
| Breach assessment + notification | `breach_notices` | 5 years |
| Subject rights requests log | `documents/pdpa/dsar-log.csv` | 5 years |
| Audit log | Configured sink | 3 years minimum |

---

## Audit Checklist

- [ ] DPO appointed and contact public
- [ ] Privacy notice covers all nine obligations
- [ ] Per-purpose consent UI verified
- [ ] Cross-border transfer mechanism in place
- [ ] Breach assessment SOP rehearsed (tabletop within 12 months)
- [ ] 3-day PDPC notification path verified
- [ ] Retention rules configured and auto-purge job running
- [ ] DNC clearance enforced in marketing flows
- [ ] Annual training completion ≥95% for staff with PI access
- [ ] Backup encryption + offsite copy verified
