# POPIA Compliance Mapping (South Africa Protection of Personal Information Act, 4 of 2013)

The Protection of Personal Information Act 4 of 2013 (POPIA) became fully enforceable on 1 July 2021. It governs processing of personal information by Responsible Parties in South Africa or where information is processed in South Africa, and is enforced by the Information Regulator.

---

## Roles

- **Responsible Party** — the customer operating the tenant; equivalent to GDPR Controller.
- **Operator** — EnterpriseCore when run as a service for the Responsible Party.
- **Data Subject** — the natural or juristic person to whom the information relates. **Note: POPIA covers juristic persons (companies), unlike most other privacy laws.**
- **Information Officer** — every Responsible Party automatically has an Information Officer (the CEO or equivalent) and must register them with the Regulator.

---

## Eight Conditions for Lawful Processing (Sections 8 to 25)

POPIA's substantive obligations are organised around eight conditions. Mapping each:

### Condition 1 — Accountability (Section 8)

The Responsible Party must ensure the conditions are met.

**EnterpriseCore feature:** Compliance dashboard at `/admin/compliance` summarises status of each control. The `compliance_attestations` table records who confirmed which control and when.

---

### Condition 2 — Processing Limitation (Sections 9 to 12)

Processing must be lawful, justified by a Section 11 ground, minimal, and from the data subject (unless an exception applies).

**EnterpriseCore feature:**
- `lawful_basis` audit dimension supports POPIA Section 11 grounds (consent, contract, legal obligation, vital interest, public-body function, legitimate interest).
- Data-minimisation toggles per field (same control as PIPL).
- Direct-from-subject collection is the default — third-party-sourced records require a `source` annotation.

---

### Condition 3 — Purpose Specification (Sections 13 to 14)

Purpose must be specific, explicitly defined, and lawful. Records must not be retained longer than necessary.

**EnterpriseCore feature:** Each processing activity in the `processing_activities` registry has an explicit, customer-edited purpose statement. Retention rules under Tenant Settings → Privacy → Retention enforce automatic deletion / anonymisation.

---

### Condition 4 — Further Processing Limitation (Section 15)

Further processing must be compatible with the original purpose.

**EnterpriseCore feature:** New features that re-purpose existing data (e.g., adding AI summarisation over historical messages) require an admin to acknowledge the compatibility check in the feature-enable flow.

---

### Condition 5 — Information Quality (Section 16)

The Responsible Party must take reasonable practical steps to ensure accuracy, currency, and completeness.

**EnterpriseCore feature:** Subject correction endpoint (`PATCH /api/v1/gdpr/data-subject`). Stale-record reports under Reports → Data Quality flag records last updated >1 year ago.

---

### Condition 6 — Openness (Sections 17 to 18)

The Responsible Party must maintain documentation of all processing operations (Section 17 — PAIA manual cross-reference) and notify subjects when collecting (Section 18 — analogous to GDPR Article 14 notice).

**EnterpriseCore feature:**
- Processing-activity registry doubles as the Section 17 documentation.
- Notice text per processing activity is rendered to subjects on collection and stored versioned.

---

### Condition 7 — Security Safeguards (Sections 19 to 22)

Section 19: appropriate technical and organisational measures.
Section 21: written contract with Operator.
Section 22: breach notification to Regulator and affected subjects "as soon as reasonably possible" after discovery.

**EnterpriseCore feature:**
- Same security baseline as GDPR/LGPD/DPDP (encryption, RBAC, IP allowlist, audit streaming, backups).
- DPA template at `docs/compliance/dpa-template-popia.md` for the customer-Operator agreement.
- Breach detection + notification workflow in `docs/INCIDENT_RESPONSE.md` with POPIA-specific timing guidance (Regulator practice: notify within 72 hours).

---

### Condition 8 — Data Subject Participation (Sections 23 to 25)

Subjects have the right to access, correct, delete, and object.

| Right | Section | Endpoint |
|---|---|---|
| Confirmation of holding | 23(1)(a) | `GET /api/v1/gdpr/data-subject` |
| Access | 23(1)(b) | `GET /api/v1/gdpr/data-subject/export` |
| Correction | 24(1)(a) | `PATCH /api/v1/gdpr/data-subject` |
| Deletion / destruction | 24(1)(b) | `DELETE /api/v1/gdpr/data-subject` |

Access requests under Section 23 follow the Promotion of Access to Information Act (PAIA) procedure — Form 2 submission, 30-day response window, fees per the PAIA fee schedule.

**EnterpriseCore feature:** PAIA Form 2 template at `documents/paia/form-2.md` and the GDPR export endpoint produces a PAIA-compatible response packet when `?format=paia` is passed.

---

## Section 27 — Special Personal Information

Religious / philosophical beliefs, race / ethnic origin, trade union membership, political persuasion, health or sex life, criminal behaviour or alleged commission of an offence, biometric information.

Same controls as GDPR Article 9 / LGPD Article 11 / PIPL Article 28: sensitive-field classification, role-gated access, opt-out from bulk exports.

---

## Section 34 — Children

Processing of personal information of children (under 18) is prohibited unless: consent of competent person, necessary for law/legal-claim, public interest with safeguards, journalistic / literary / artistic expression, deliberately made public by child.

**EnterpriseCore feature:** Same children-data controls as PIPL/DPDP.

---

## Section 57 — Prior Authorisation by the Regulator

Required for processing involving: unique identifiers for purposes other than original, credit reporting, transfer of special PI / children's PI to a country without adequate protection, automated decisions with legal effect.

**Customer action:** Where applicable, submit Form 3 to the Information Regulator before processing begins. EnterpriseCore stores the authorisation reference in `compliance_attestations`.

---

## Section 71 — Automated Decision-Making

A subject must not be subject to a decision based solely on automated processing that has legal/substantial effects, unless taken in connection with a contract, authorised by law with safeguards, or with subject's consent.

**EnterpriseCore feature:** Same automated-decision audit and human-review mechanism as PIPL.

---

## Section 72 — Cross-Border Transfer

Transfer to a third country allowed if the recipient is subject to a law / binding rules / agreement providing adequate protection, or with subject's consent, or necessary for contract performance, or for the subject's benefit and consent not reasonably obtainable.

**EnterpriseCore feature:** Same cross-border register as PIPL; default position is single-region storage in `af-south-1` for ZA-residency tenants.

---

## Records to Maintain

| Record | Location | Retention |
|---|---|---|
| Information Officer registration | `compliance_attestations` | Permanent |
| Section 17 processing documentation | `processing_activities` | Life of activity |
| Consents | `consent_records` | Life + 3 years |
| Section 22 breach register | `breach_notices` | 5 years |
| PAIA requests received | `documents/paia/log.csv` | 5 years |
| Audit log | Configured sink | 5 years |

---

## Audit Checklist

- [ ] Information Officer registered with the Regulator
- [ ] PAIA manual published
- [ ] Operator contract signed (POPIA Section 21)
- [ ] Cross-border register accurate
- [ ] Sensitive PI handling controls verified
- [ ] Children's PI handling controls verified (if applicable)
- [ ] Section 57 prior authorisation in place (if applicable)
- [ ] Breach response timeline verified by tabletop in last 12 months
- [ ] Backup encryption + offsite copy verified
- [ ] Annual SOC2 / ISO27001 audit current
