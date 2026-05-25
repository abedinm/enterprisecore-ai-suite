# UK GDPR Quick Reference

Since 1 January 2021, the UK has its own retained version of the EU General Data Protection Regulation, known as the **UK GDPR**, supplemented by the **Data Protection Act 2018 (DPA 2018)**. It is enforced by the **Information Commissioner's Office (ICO)**.

For practical purposes UK GDPR mirrors EU GDPR. This document highlights the differences that matter operationally and points the reader to the main GDPR mapping in `docs/GDPR.md`.

---

## What Is the Same

All substantive obligations match EU GDPR:
- Lawful bases (Article 6)
- Special category processing (Article 9)
- Data subject rights (Articles 12 to 22)
- Records of processing (Article 30)
- Security of processing (Article 32)
- Breach notification (Article 33) — 72 hours to the ICO
- DPIA triggers (Article 35)

Refer to `docs/GDPR.md` for the EnterpriseCore feature mappings — every one of them satisfies the UK GDPR analogue.

---

## Key Differences

### Regulator

- **EU GDPR:** lead supervisory authority in the Organisation's main establishment EU country.
- **UK GDPR:** the Information Commissioner's Office (ICO).

EnterpriseCore tenants targeting UK individuals must designate the ICO as the primary regulator for breach notification and subject complaints.

---

### Adequacy and Transfers

The UK and the EU have mutual adequacy decisions (as of 28 June 2021, valid through 27 June 2025 with the option to extend). This means data can flow freely between the UK and the EEA in both directions.

For transfers from the UK to countries that are not on the UK's adequacy list, the UK has its own:
- **UK International Data Transfer Agreement (IDTA)** — replaces the EU SCCs.
- **UK Addendum to the EU SCCs** — for organisations already using EU SCCs.

**EnterpriseCore feature:** Cross-border register entries for UK-sourced transfers reference one of the above. Templates at `documents/uk-gdpr/idta-template.md` and `documents/uk-gdpr/eu-addendum.md`.

---

### Age of Consent for ISS

UK GDPR / DPA 2018 sets the age of consent for Information Society Services at **13**, vs. the EU default of 16 (member states can lower to 13 — most have).

**EnterpriseCore feature:** Tenant Settings → Privacy → Children includes a slider for the age threshold; default value is 13 for UK-residency tenants and 16 for EU-residency tenants.

---

### Demonstrating Compliance to the ICO

The ICO publishes a Records of Processing template and a self-assessment checklist that differ slightly from the European Data Protection Board's. EnterpriseCore's processing-activity registry export (`GET /api/v1/admin/processing-activities/export?format=ico`) produces a CSV in the ICO template format.

---

### PECR (Privacy and Electronic Communications Regulations)

Separate from UK GDPR but enforced by the ICO. Covers cookies, electronic marketing, and traffic data.

Practical implications for EnterpriseCore:
- The marketing module must respect prior-consent (opt-in) for electronic marketing to UK individuals, with a soft-opt-in exception for existing customers.
- Cookies: the customer must publish a cookie banner; EnterpriseCore's frontend ships with a configurable cookie consent component.

---

### DPO Requirement

UK GDPR requires a DPO in the same circumstances as EU GDPR (public authority, large-scale systematic monitoring, large-scale special category processing). The DPO need not be UK-based.

**EnterpriseCore feature:** Same Tenant Settings → Compliance → DPO field.

---

### UK Representative

UK GDPR Article 27 requires Controllers / Processors outside the UK to appoint a UK Representative (analogous to the EU representative for non-EU Controllers).

**EnterpriseCore feature:** Tenant Settings → Compliance → UK Representative captures the appointed firm's name and contact.

---

## Subject Rights — Channel and Timing

Same as EU GDPR: 30 days, free of charge for the first request (manifestly unfounded / excessive requests can incur a fee or be refused).

All EnterpriseCore subject-rights endpoints (export / correct / delete / object) satisfy UK GDPR identically.

---

## Audit Checklist

- [ ] ICO registered as the primary regulator
- [ ] UK Representative appointed (if Controller / Processor outside the UK)
- [ ] UK IDTA or EU-SCC Addendum on file for any transfer to non-adequate countries
- [ ] Cookie consent component configured for UK-residency tenants
- [ ] PECR-compliant marketing flows verified
- [ ] Age threshold set to 13 for UK-residency tenants
- [ ] Standard GDPR controls verified (see `docs/GDPR.md` checklist)

For the full control-by-control mapping refer to `docs/GDPR.md`. This document only enumerates the UK-specific deltas.
