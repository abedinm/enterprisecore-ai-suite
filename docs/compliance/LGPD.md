# LGPD Compliance Mapping (Brazil Lei Geral de Proteção de Dados, Lei 13.709/2018)

EnterpriseCore tenants processing personal data of natural persons in Brazil, or where the data was collected in Brazil, fall under the LGPD. This document maps each major statutory article to the EnterpriseCore feature, customer configuration step, or evidence that satisfies it.

The LGPD is enforced by the **Autoridade Nacional de Proteção de Dados (ANPD)**. Fines reach 2% of Brazil revenue, capped at R$50 million per infraction.

---

## Roles

- **Controlador** (Controller) — the customer operating the tenant.
- **Operador** (Processor) — EnterpriseCore when run as a service for the Controller.
- **Titular** — the data subject.
- **Encarregado** (DPO) — the person designated as the contact between Controlador, Titulares, and the ANPD.

---

## Article 7 — Legal Bases for Processing

Ten legal bases: consent, legal obligation, public administration, research, contract performance, judicial process, life protection, health, legitimate interest, credit protection.

**EnterpriseCore feature:** Every personal-data column writes a `lawful_basis` audit entry tagged with one of the LGPD bases. Default mappings:
- HR data → `contract_performance`
- Billing → `legal_obligation` (tax compliance)
- Marketing emails → `consent`
- Audit logs → `legitimate_interest`
- Health data — requires explicit opt-in via `POST /api/v1/gdpr/consent` with `category="health"`.

**Customer action:** Review the default mappings in Tenant Settings → Privacy → Legal Bases and override where needed.

**Evidence:** `backend/app/services/gdpr_service.py` `LAWFUL_BASIS_MAP`.

---

## Article 8 — Consent

Consent must be given in writing or by another means demonstrating the Titular's will, free, informed, and unambiguous, for a specific purpose. Blanket consent ("for all purposes") is invalid.

**EnterpriseCore feature:** Consent records are purpose-scoped. The UI signup component renders one toggle per purpose. The withdrawal endpoint (`DELETE /api/v1/gdpr/consent/{id}`) is symmetric with the grant endpoint.

---

## Article 9 — Information to be Provided

The Titular must be informed of: purpose, processing type, duration, controller identity, contact info, shared parties, controller responsibilities, and rights.

**EnterpriseCore feature:** The privacy notice template (`documents/privacy_notice/template-lgpd.md`) contains all nine required disclosures. Each tenant uploads a localised version.

---

## Article 11 — Sensitive Data

Sensitive data (racial/ethnic origin, religion, political opinion, union membership, religion/philosophy, health/sexual life, genetic/biometric) requires specific and prominent consent OR a narrow legal exception.

**EnterpriseCore feature:** Fields flagged sensitive in the `field_classification` table cannot be queried by general routes; access requires a `sensitive:read` role permission. Bulk exports refuse to include sensitive fields unless `include_sensitive=true` is explicitly passed AND the requesting user holds `sensitive:export`.

**Evidence:** `backend/tests/test_rbac.py::test_sensitive_export_denied_without_permission`.

---

## Articles 17 to 22 — Rights of the Titular

| Right | LGPD Article | Endpoint |
|---|---|---|
| Confirmation of processing | 18(I) | `GET /api/v1/gdpr/data-subject` |
| Access | 18(II) | `GET /api/v1/gdpr/data-subject/export` |
| Correction | 18(III) | `PATCH /api/v1/gdpr/data-subject` |
| Anonymisation / blocking / deletion | 18(IV) | `DELETE /api/v1/gdpr/data-subject?mode=anonymise|block|delete` |
| Portability | 18(V) | `GET /api/v1/gdpr/data-subject/export?format=json|csv` |
| Deletion of consented data | 18(VI) | covered by `DELETE` |
| Information about shared parties | 18(VII) | `GET /api/v1/gdpr/data-subject/shared-with` |
| Information about non-consent | 18(VIII) | covered in privacy notice |
| Revocation of consent | 18(IX) | `DELETE /api/v1/gdpr/consent/{id}` |

SLA: 15 days per Article 19 §1 II.

---

## Article 33 — International Transfers

Transfers permitted to countries with adequate protection, by SCCs, by binding corporate rules, by Titular consent, or for specific legal exceptions.

**EnterpriseCore feature:**
- `DATA_RESIDENCY_REGION` deployment env enforces single-region storage.
- For cross-region replicas (DR), the deployment must record an SCC pointer in `documents/sccs/` and reference it from `docs/DISASTER_RECOVERY.md`.

**Customer action:** Upload your ANPD-approved SCC and reference it in your DPIA.

---

## Article 37 — Records of Processing Activities

The Controller must keep records of processing activities, especially when based on legitimate interest.

**EnterpriseCore feature:** The `processing_activities` table is populated by the bootstrap migration with one row per default processing activity (auth, HR, billing, etc.). Additional activities are added via Tenant Settings → Privacy → Activities.

---

## Article 38 — DPIA (Relatório de Impacto)

A DPIA is required for high-risk processing.

**EnterpriseCore feature:** `documents/dpia/template-lgpd.md` provides the structure: description of processing, necessity/proportionality assessment, safeguards, risks to Titulares, mitigations.

---

## Article 41 — Encarregado (DPO)

The Controller must indicate an Encarregado. Their identity and contact must be public.

**EnterpriseCore feature:** Tenant Settings → Compliance → Encarregado captures name, email, address. The tenant's privacy page renders this publicly.

---

## Articles 46 to 49 — Security and Best Practices

Article 46: the Controller and Operator must adopt security, technical, and administrative measures.

EnterpriseCore controls (mirrors DPDP §32):
- Encryption at rest and in transit
- RBAC + IP allowlist
- Audit log streaming
- Quarterly access reviews
- Annual penetration test (see `docs/SOC2_CONTROLS.md`)
- Backup encryption + offsite copy (`scripts/backup/`)

Article 48: incidents must be notified to the ANPD and to affected Titulares in "reasonable time" (ANPD guidance: 2 working days).

**EnterpriseCore feature:** Breach detection via audit-stream anomaly rules, notification queue, ANPD report templates in `docs/INCIDENT_RESPONSE.md` (Brazil section).

---

## Article 50 — Good Practices and Governance

Optional but recommended privacy programme covering: training, internal monitoring, response plans, complaint mechanisms.

**EnterpriseCore feature:** Templates and checklists in `docs/SOC2_CONTROLS.md` adapt to LGPD §50.

---

## Children and Adolescents (Article 14)

Processing data of children requires specific, highlighted parental consent. Best-interest standard applies.

**EnterpriseCore feature:** Same children-data controls as DPDP §9 — the underlying `is_minor` and `parent_consent_evidence` fields are jurisdiction-agnostic.

---

## Records and Retention

| Record | Location | Retention |
|---|---|---|
| Consents and revocations | `consent_records` | Life of consent + 5 years |
| Processing activity registry | `processing_activities` | Life of activity |
| DPIA | `documents/dpia/` | Life + 5 years |
| Incident register | `breach_notices` | 5 years |
| Audit log | Configured sink | 5 years minimum |

---

## Audit Checklist

- [ ] Encarregado indicated and contact public
- [ ] Privacy notice in Portuguese
- [ ] Legal basis mapping reviewed
- [ ] Sensitive-data RBAC enforced
- [ ] DPIA on file for high-risk processing
- [ ] SCC on file for any cross-border transfer
- [ ] Audit streaming target reachable
- [ ] Backup encryption + offsite copy verified
- [ ] Incident response playbook reviewed in last 12 months
