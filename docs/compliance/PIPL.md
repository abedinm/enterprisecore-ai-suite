# PIPL Compliance Mapping (China Personal Information Protection Law, 2021)

The Personal Information Protection Law (PIPL) of the People's Republic of China governs the handling of personal information (PI) of natural persons within the territory of China, and also extraterritorially when processing PI of persons in China for the purpose of providing products/services or analysing/evaluating their behaviour.

EnterpriseCore deployments that fall under PIPL require additional controls beyond the GDPR baseline, particularly around cross-border transfer, separate consent for sensitive categories, and the appointment of a designated representative in China for foreign Handlers.

---

## Roles

- **Personal Information Handler** (个人信息处理者) — analogous to a Controller. The customer operating the tenant.
- **Entrusted Party** (受托方) — analogous to a Processor. EnterpriseCore when run as a managed service.
- **Personal Information Subject** — the data subject.
- **Designated Domestic Representative** — required for Handlers outside China that process PI of persons in China.

---

## Articles 5 to 9 — General Principles

PIPL requires lawful, justified, necessary, and good-faith processing for explicit, reasonable purposes; the minimum scope of data; transparency; quality; security; and accountability.

**EnterpriseCore feature:** Per-field data minimisation through optional column collection (Tenant Settings → Privacy → Fields lets the customer turn off columns the product doesn't need — e.g., date_of_birth, address — so they aren't collected at all). Audit logs capture every PI access with purpose annotation.

---

## Article 13 — Lawful Bases

Seven bases: consent, contract performance, statutory duty, public-health emergency, news/public-interest reporting, publicly disclosed information, other circumstances stipulated by law.

**EnterpriseCore feature:** The same `lawful_basis` audit dimension used for GDPR/LGPD maps each PIPL basis. PIPL-only bases (public-health emergency, news/public-interest) require manual flagging by an admin user — they're not automatically inferred.

---

## Articles 14 to 16 — Consent

Consent must be voluntary, explicit, and based on full information. Withdrawal must be available. **Bundled consent** (one toggle for multiple purposes) is invalid. PIPL requires **separate consent** for:
- Sensitive PI (Article 29)
- Cross-border transfer (Article 39)
- Sharing with another Handler (Article 23)
- Public disclosure (Article 25)
- Use for automated decision-making (Article 24)

**EnterpriseCore feature:** Consent records are purpose-scoped and the consent UI is configured to require a separate explicit toggle for each of the five separate-consent categories above when relevant.

**Evidence:** `frontend/src/components/PrivacyConsent.tsx` renders distinct toggles per category.

---

## Article 17 — Notice

The Handler must inform the subject of: Handler identity and contact, purposes and methods, categories of PI, retention period, methods to exercise rights, and any further matters required by law.

**EnterpriseCore feature:** Privacy notice template `documents/privacy_notice/template-pipl.md` covers all required disclosures. Notice is rendered in simplified Chinese for tenants with `locale=zh-CN`.

---

## Article 23 — Sharing with Other Handlers

When PI is shared with another Handler, the original Handler must inform the subject of the recipient's identity/contact and obtain separate consent. The original Handler remains responsible for the recipient's handling unless agreed otherwise.

**EnterpriseCore feature:** The Integrations module captures every external destination (Slack, Stripe, Webhook URL, etc.) in `integrations` table. When a new integration is added, a popup requires the admin to confirm the data categories shared and triggers a consent refresh prompt for affected subjects.

---

## Articles 24 — Automated Decision-Making

Subjects have the right to demand human review and to refuse decisions made solely by automated means that significantly affect them.

**EnterpriseCore feature:** AI features (resume screening, document classification, etc.) write `automated_decision=true` to the audit log. The audit dashboard exposes `GET /api/v1/admin/automated-decisions` for compliance review. End users can request human review through the grievance endpoint.

---

## Article 28 — Sensitive Personal Information

Sensitive PI: biometric, religious belief, specific identity, medical/health, financial accounts, location tracking, PI of minors under 14.

Requires: separate consent, specific purpose and sufficient necessity, strict protection measures.

**EnterpriseCore feature:** Same `sensitive` field classification as LGPD. Additional PIPL-specific category: location tracking. The `Location` field is disabled by default and turned on per-tenant only after a "sensitive PI" toggle.

---

## Articles 38 to 43 — Cross-Border Transfer (most operationally relevant)

Cross-border transfer of PI of persons in China requires **one** of:

1. **Security assessment** by the Cyberspace Administration of China (CAC) — mandatory for Critical Information Infrastructure Operators, for transfers of PI of >1 million persons, for cumulative transfers of >100 000 persons, or for transfers of sensitive PI of >10 000 persons in a calendar year.
2. **Standard Contract** filed with the local CAC office (the China SCC, published 2023).
3. **Certification** by a CAC-approved body.
4. **Other conditions** prescribed by CAC.

Plus: separate consent from the subject, a Personal Information Protection Impact Assessment (PIPIA), and a notice covering recipient identity, contact, purposes, categories, and how to exercise rights with the recipient.

**EnterpriseCore feature:**
- `DATA_RESIDENCY_REGION=cn` enforces single-region storage inside China.
- For deployments that must transfer (e.g., to a global headquarters), the `cross_border_transfer_register` table records destination, legal basis, volume, and CAC filing reference.
- The PIPIA template at `documents/dpia/template-pipl.md` covers all CAC-required elements.

**Customer action:**
- Decide which transfer mechanism applies based on volume.
- File the China SCC with the provincial CAC and store the filing receipt in `documents/sccs/cn-{date}.pdf`.
- Update the cross-border register before transfers begin.
- Refresh subject consent referencing the new recipient(s).

**Evidence:** `backend/tests/test_data_residency.py::test_cn_residency_blocks_cross_border_write`.

---

## Articles 44 to 50 — Rights of the Subject

| Right | Article | Endpoint |
|---|---|---|
| Know and decide about processing | 44 | privacy notice + consent screens |
| Access and copy | 45 | `GET /api/v1/gdpr/data-subject/export` |
| Portability (to another Handler meeting CAC criteria) | 45 | `GET /api/v1/gdpr/data-subject/export?format=json` |
| Correction | 46 | `PATCH /api/v1/gdpr/data-subject` |
| Deletion | 47 | `DELETE /api/v1/gdpr/data-subject` |
| Explanation of rules | 48 | privacy notice |
| Rights of deceased | 49 | `POST /api/v1/gdpr/legacy-claim` (next-of-kin endpoint) |
| Convenient channel | 50 | grievance endpoint + email contact |

SLA: PIPL does not specify a deadline; industry practice is 15 days (aligning with the China SCC).

---

## Article 51 — Security Obligations

Handlers must:
- Formulate internal management systems and operating rules
- Implement classified management of PI
- Adopt technical security measures (encryption, de-identification)
- Reasonably determine access rights and conduct security education
- Formulate emergency response plans
- Other measures required by law

EnterpriseCore controls (consistent with GDPR/LGPD/DPDP plus PIPL-specific extras):
- AES-256 at rest, TLS 1.2+ in transit.
- RBAC with 4 roles + custom policies.
- IP allowlist per tenant.
- Audit streaming to SIEM.
- China-specific: support for CCB (国密) algorithms via libsodium-compat fork if `CRYPTO_PROFILE=gm` is set at deployment.

---

## Article 52 — Person in Charge / Designated Representative

Handlers above a certain threshold (the CAC has indicated a threshold but not formally codified) must designate a Person in Charge of PI Protection. Foreign Handlers must designate a domestic Representative in China and report their contact to the relevant authority.

**EnterpriseCore feature:** Tenant Settings → Compliance → China stores the Person in Charge and the Domestic Representative contacts, surfacing them in the privacy notice.

---

## Article 55 — PIPIA Triggers

A PIPIA is mandatory before:
- Processing sensitive PI
- Using PI for automated decision-making
- Entrusting PI to a third party
- Sharing with another Handler
- Publicly disclosing PI
- Cross-border transfer
- Other processing with significant impact

**Customer action:** Run a PIPIA using `documents/dpia/template-pipl.md` for each triggering activity; store the outcome in `documents/dpia/cn-*.md`.

---

## Articles 57 to 58 — Incident Response

In a security incident the Handler must take immediate remedial measures, notify the regulator and affected subjects, unless effective measures prevent harm — in which case notification can be deferred.

**EnterpriseCore feature:** Same incident response playbook as the global runbooks. China-specific addendum in `docs/INCIDENT_RESPONSE.md` covers CAC notification template and the 24-hour reporting expectation that has become market norm.

---

## Records to Maintain

| Record | Location | Retention |
|---|---|---|
| Consents (including separate consents) | `consent_records` | 3 years post-withdrawal |
| Cross-border register | `cross_border_transfer_register` | Permanent |
| PIPIA outcomes | `documents/dpia/cn-*` | Permanent |
| Incident reports | `breach_notices` | 3 years minimum |
| Audit logs | Configured sink | 3 years minimum (Cybersecurity Law) |

---

## Audit Checklist

- [ ] `DATA_RESIDENCY_REGION=cn` set, verified by data-residency test
- [ ] Person in Charge designated and contact public
- [ ] Domestic Representative designated (if Handler is foreign)
- [ ] Separate consent toggles for sensitive PI, cross-border, sharing, automated decisions
- [ ] PIPIA completed for every triggering activity
- [ ] Cross-border transfer mechanism filed (security assessment / SCC / certification)
- [ ] Privacy notice in simplified Chinese
- [ ] Automated decision-making review queue staffed
- [ ] Audit logs retained for 3+ years
- [ ] Incident playbook updated with CAC contact and 24-hour timeline
