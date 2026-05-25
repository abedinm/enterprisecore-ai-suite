# Incident response

This document defines how EnterpriseCore handles production incidents. It applies to the SaaS hosted instance and is shipped as a template for self-hosted customers to adapt.

The audience is engineers on call, incident commanders, customer-success leads, and executives who need to know when to be involved.

---

## Severity definitions

We use three severity levels. The severity is set at detection, may be upgraded as the picture clears, and is set by the on-call engineer (escalating to incident commander where ambiguous).

### Sev 1

Customer-facing outage or data integrity issue, OR a security event with confirmed customer impact.

Examples:

- Application is unreachable for ≥1 tenant for ≥5 minutes.
- Database is read-only / failing writes.
- Confirmed unauthorised access to a tenant's data.
- Confirmed data loss without a recoverable backup within RPO.
- Stripe webhook outage causing incorrect billing state.

Response: page within 5 minutes. Incident commander assigned within 10 minutes. Customer status page posted within 15 minutes. Hourly internal updates until resolved.

### Sev 2

Customer-impacting degradation, not full outage.

Examples:

- One feature broken (e.g., SSO failing for one tenant, webhooks failing for a subset of customers).
- Elevated error rate or latency, SLO at risk but not breached.
- A non-critical integration is down (search index lag, audit stream backed up).

Response: page during business hours, queue for next business hour overnight. Status page only if customer-facing. Updates every 4 hours.

### Sev 3

Minor issue with workaround.

Examples:

- Single-user cosmetic bug.
- Internal tool failure (admin dashboard widget broken).
- Long-running background job stuck (no customer impact).

Response: file a ticket, fix in normal sprint cadence. No page.

---

## Lifecycle

The five phases each have a clear owner and exit criteria.

### 1. Detect

Triggered by an alert, a customer ticket, or an engineer noticing something off.

**Owner:** the alert pipeline (Alertmanager / PagerDuty / Sentry).
**Exit:** the on-call engineer has acknowledged the page and confirmed it's real (or dismissed as false-positive with a note).

### 2. Triage

Establish severity, scope, and whether to declare an incident.

**Owner:** the on-call engineer.
**Exit:**
- Severity set.
- Scope (which tenants, which feature) recorded in the incident channel.
- Incident commander assigned (the on-call engineer can be the commander for Sev 2/3; a different person should be commander for Sev 1).
- Customer-facing status update posted if Sev 1.

### 3. Mitigate

Get customer impact back to baseline. Mitigation is NOT root-cause fix; do not let "I want to understand why" delay restoring service. Roll back, fail over, throttle the noisy tenant — whatever stops the bleeding.

**Owner:** the incident commander, delegating to engineers.
**Exit:** SLO restored OR customers are no longer impacted (e.g., workaround issued).

### 4. Resolve

Restore the system to a permanent, healthy state — typically by deploying the actual fix.

**Owner:** the engineer who owns the affected component.
**Exit:**
- Production is on the fixed code.
- All temporary mitigations rolled back (rate limits removed, fallback providers restored).
- Customer status page marked Resolved.

### 5. Postmortem

Blameless review of what happened, what went well, what didn't, and what to change. Required for every Sev 1 and Sev 2 incident.

**Owner:** the incident commander.
**Exit:** postmortem document published within 5 business days of incident close; action items tracked in the engineering backlog with owners.

---

## Customer-facing status update — template

Use plain language. Avoid jargon. Update at least hourly during Sev 1, more often if scope changes.

**Investigating:**

> We are investigating reports of [symptom — e.g., login errors for some customers]. The team is actively working on the issue. Next update by [time].

**Identified:**

> We have identified the cause of [symptom]. A fix is in progress. We expect to restore service by approximately [time]. Next update by [time].

**Monitoring:**

> A fix has been deployed for [symptom]. We are monitoring to confirm full recovery. Next update by [time].

**Resolved:**

> [Symptom] has been resolved as of [time]. We will publish a post-incident review within five business days.

Avoid:

- Mentioning the specific failing component if it tells an attacker something they don't know (security incidents).
- Promising root cause before postmortem is complete.
- Blaming a specific person or team.

---

## Internal communication channels

- `#ec-incidents` — incident channel. Sev 1 declared here automatically by the on-call paging hook.
- `#ec-ops` — day-to-day ops chatter. Lower-severity issues that haven't risen to an incident.
- `#ec-status` — read-only feed mirrored to the customer status page.
- `#ec-security` — security-sensitive incidents. Restricted membership. Sev 1 security incidents are tracked here AND `#ec-incidents`, with details sanitised in the latter.

For every Sev 1:

1. Create a dedicated channel `#inc-YYYY-MM-DD-<slug>`.
2. Pin the incident document Google Doc / Notion page.
3. Tag commander, comms lead, and the on-call engineer in the topic.

---

## Roles during a Sev 1

- **Incident Commander (IC).** Owns the incident end-to-end. Sets cadence. Decides when to mitigate vs investigate. Calls escalations. The IC does NOT type code during the incident — they coordinate.
- **Engineering lead.** Owns the technical fix. Delegates investigation to subject-matter engineers.
- **Communications lead.** Owns the status page and customer comms. Translates engineering progress into customer-facing updates.
- **Subject-matter engineer(s).** The people actually running queries, writing patches, doing the work.

For Sev 2 the IC may also be the engineering lead and the comms lead. For Sev 1 they should be different people if at all possible.

---

## Postmortem template

Save to `docs/postmortems/YYYY-MM-DD-<slug>.md`. Postmortems are blameless — describe the system's failure, not a person's.

```markdown
# Postmortem — <slug>

**Date:** YYYY-MM-DD
**Severity:** sev1 / sev2
**Duration:** start → end (HH:MM)
**Tenants affected:** count and named list if Sev 1
**Author:** name
**Status:** draft / in review / published

## Summary

One paragraph. What happened in plain English.

## Impact

- Customers affected: N tenants, M users.
- Functional impact: which features were broken, how badly.
- Financial impact: refunds, credits, lost revenue (estimate).
- SLO impact: error budget consumed.

## Timeline

All times in UTC.

- HH:MM — change deployed.
- HH:MM — alert fired.
- HH:MM — on-call acknowledged.
- HH:MM — severity set to sev1.
- HH:MM — mitigation applied.
- HH:MM — SLO restored.
- HH:MM — root cause identified.
- HH:MM — fix deployed.
- HH:MM — incident closed.

## Root cause

The 5-whys. Walk down from "what happened" to the deepest fixable layer.

## What went well

- Bullet list. Detection time, response coordination, customer comms, rollback procedure.

## What didn't go well

- Bullet list. Be specific. "Alerts were too noisy and we missed the real one for 8 minutes."

## Action items

| Priority | Owner | Action | Due |
|---|---|---|---|
| P0 | name | concrete thing | date |
| P1 | name | concrete thing | date |
| P2 | name | concrete thing | date |

Each action item must have an owner and a due date. P0 items must close within 30 days.
```

---

## Jurisdiction-specific incident notes

These are quick pointers; the compliance docs contain the canonical timelines.

- **EU GDPR / UK GDPR** — 72 hours to notify the supervisory authority. See `docs/GDPR.md` / `docs/compliance/UK_GDPR.md`.
- **Singapore PDPA** — 3 calendar days to PDPC for notifiable breaches. See `docs/compliance/PDPA_SG.md`.
- **South Korea PIPA** — "without delay" — PIPC guidance 72 hours, plus subject notification. See `docs/compliance/PIPA.md`.
- **Brazil LGPD** — "reasonable time," ANPD guidance 2 working days. See `docs/compliance/LGPD.md`.
- **South Africa POPIA** — "as soon as reasonably possible" — Regulator practice 72 hours. See `docs/compliance/POPIA.md`.
- **Japan APPI** — "promptly" — PPC guidance 3-5 days preliminary, 30 days final. See `docs/compliance/APPI.md`.
- **China PIPL** — market norm 24 hours to CAC for material incidents. See `docs/compliance/PIPL.md`.
- **Quebec Law 25** — "as soon as possible" once risk-of-serious-injury is confirmed. See `docs/compliance/Quebec_Law25.md`.
- **India DPDP** — "in such form and manner as may be prescribed" — keep evidence ready. See `docs/compliance/DPDP.md`.
