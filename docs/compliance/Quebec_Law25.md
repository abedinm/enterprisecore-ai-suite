# Quebec Law 25 Compliance Mapping (Canada — An Act to modernize legislative provisions as regards the protection of personal information)

**Bill 64**, now known as **Law 25**, modernised Quebec's private-sector privacy law (formerly known as Quebec's Act respecting the protection of personal information in the private sector). It was rolled out in three phases:

- **22 September 2022** — privacy officer designation, breach reporting, incident register, biometric reporting.
- **22 September 2023** — main obligations: consent rules, PIA requirement, transparency, transfer restrictions, profiling notice, etc.
- **22 September 2024** — data portability right.

Law 25 is enforced by the **Commission d'accès à l'information du Québec (CAI)**.

---

## Roles

- **Enterprise** — the customer (an organisation carrying on an enterprise in Quebec or whose data subjects are in Quebec).
- **Service Provider** — EnterpriseCore when run for the Enterprise.
- **Person Concerned** — the data subject.
- **Person Responsible for the Protection of Personal Information** — the privacy officer; by default the highest-ranking person in the Enterprise, who may delegate in writing.

---

## Privacy Officer (Article 3.1, in force since 22 Sep 2022)

Every Enterprise must designate a person responsible for PI protection and **publish their title and contact** on the Enterprise's website.

**EnterpriseCore feature:** Tenant Settings → Compliance → Quebec Privacy Officer captures title, name, email, phone. Public-facing privacy page renders this automatically.

---

## Confidentiality Incident Register and Notification (Article 3.5, in force since 22 Sep 2022)

The Enterprise must keep a register of "confidentiality incidents" — unauthorised access, use, communication, or loss of personal information.

If an incident presents a "risk of serious injury," the CAI and affected Persons Concerned must be notified.

Penalties for failure: up to CAD 25M or 4% of worldwide turnover (whichever is higher).

**EnterpriseCore feature:**
- `breach_notices` table doubles as the Law 25 incident register; entries capture nature, date discovered, scope, mitigations, and notification status.
- Severity assessment workflow in `docs/INCIDENT_RESPONSE.md` (Quebec section) defines the "risk of serious injury" criteria.
- Notification templates in French and English.

---

## Biometric Reporting (Article 45 of the Act respecting the legal framework for IT, since 22 Sep 2022)

Use of biometric characteristics to verify or confirm identity must be **declared to the CAI 60 days before commencement**.

**EnterpriseCore feature:** Biometric processing is opt-in. When enabled, an admin prompt requires the customer to confirm the CAI declaration reference (stored in `compliance_attestations`).

---

## Consent (Articles 12 to 14, in force since 22 Sep 2023)

Consent must be "manifest, free, enlightened and given for specific purposes." It must be requested for each purpose, in clear and simple terms, separately from any other information.

Consent of a minor under 14 must be given by the holder of parental authority. From 14, the minor can consent themselves.

**EnterpriseCore feature:**
- Per-purpose consent UI, no bundling.
- Children-data handling supports the Quebec-specific 14-year threshold via the per-tenant age slider.

---

## Transparency on Automated Decisions and Profiling (Article 12.1, in force since 22 Sep 2023)

The Enterprise must inform the Person Concerned of: the use of automated decision-making, the principal factors involved, and the right to request human review.

**EnterpriseCore feature:** Same automated-decision audit and human-review queue as PIPL / POPIA. The privacy notice automatically lists features that involve automated decisions.

---

## Privacy Impact Assessment (Article 3.3, in force since 22 Sep 2023)

A PIA is required before:
- Any acquisition, development, or overhaul of an information system involving PI;
- Communication of PI outside Quebec (transfer).

**EnterpriseCore feature:** PIA template at `documents/quebec/pia-template.md`. Stored outcomes in `documents/dpia/qc-*.md`.

---

## Transfer Outside Quebec (Article 17, in force since 22 Sep 2023)

Before transferring PI outside Quebec, the Enterprise must conduct a PIA assessing whether the destination provides protection equivalent to Law 25. If yes, the transfer can proceed under a written agreement.

**EnterpriseCore feature:**
- Cross-border register entries for QC-sourced transfers.
- Equivalency-assessment template at `documents/quebec/equivalency-template.md`.
- `DATA_RESIDENCY_REGION=qc-central-1` (or `ca-central-1` with QC-residency tenant flag) enforces single-region storage.

---

## Rights of the Person Concerned

| Right | Article | Endpoint | SLA |
|---|---|---|---|
| Access | 27 | `GET /api/v1/gdpr/data-subject/export` | 30 days |
| Correction | 28 | `PATCH /api/v1/gdpr/data-subject` | 30 days |
| Right to be informed of automated decisions | 12.1 | privacy notice + dashboard | n/a |
| Right to cease dissemination / de-indexation | 28.1 | `POST /api/v1/gdpr/right-to-be-forgotten` | 30 days |
| Right to portability (since 22 Sep 2024) | 27 | `GET /api/v1/gdpr/data-subject/export?format=json` | 30 days |

---

## Right to Cease Dissemination / De-indexation (Article 28.1)

A unique Law 25 right: a Person Concerned can require that an Enterprise cease dissemination of their PI or de-index hyperlinks providing access to that information when:
- Dissemination contravenes the law or a court order; OR
- Serious injury arises from the dissemination and outweighs the public-interest / right to know.

**EnterpriseCore feature:** The `right_to_be_forgotten` endpoint records the request, removes the data from public-facing surfaces (web profile, embeds, public links), and updates the search index to exclude the resource.

---

## Data Portability (Article 27 §3, in force since 22 Sep 2024)

Right to receive computerised PI in a structured, commonly-used format and to require its communication to another person/body.

**EnterpriseCore feature:** Export endpoint emits JSON / CSV. Direct-to-receiver transmission is queued via the integrations webhook framework when the receiver is configured.

---

## Privacy by Default (Article 9.1, in force since 22 Sep 2023)

Enterprises offering a technological product or service to the public must, by default, ensure the parameters of the product or service provide the highest level of confidentiality, without the Person Concerned's intervention.

**EnterpriseCore feature:** Default tenant settings for QC-residency tenants set:
- Public profile = off
- Marketing emails = off
- Sharing with integrations = off
- Telemetry = anonymised

Customers can opt in to broader settings on a per-feature basis.

---

## Records to Maintain

| Record | Location | Retention |
|---|---|---|
| Privacy Officer designation and contact | `compliance_attestations` | Permanent |
| Confidentiality incident register | `breach_notices` | Permanent (no specified floor) |
| PIA outcomes | `documents/dpia/qc-*` | Life of processing + 5 years |
| Cross-border equivalency assessments | `documents/quebec/equivalency-*` | Life of transfer + 5 years |
| Consent records | `consent_records` | Life + 5 years |
| Subject rights requests log | `documents/quebec/dsar-log.csv` | 5 years |

---

## Audit Checklist

- [ ] Privacy Officer designated and contact public
- [ ] Confidentiality incident register active
- [ ] Biometric declaration filed (if applicable)
- [ ] Per-purpose consent UI verified, French + English versions
- [ ] Automated decision notice rendered in privacy notice
- [ ] PIA completed before each new system / overhaul / transfer
- [ ] Cross-border equivalency assessment on file
- [ ] Right to cease dissemination / de-indexation workflow tested
- [ ] Portability endpoint reachable
- [ ] Privacy-by-default settings audited
- [ ] Annual review by Privacy Officer documented
