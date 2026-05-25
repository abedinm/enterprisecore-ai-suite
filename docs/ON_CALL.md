# On-call

This document describes the EnterpriseCore on-call rotation, what's expected of the person on call, and the tools and access they need.

It is shipped as a template for self-hosted customers; adapt the schedule, escalation tree, and compensation policy to your organisation.

---

## Schedule

- **Cadence:** weekly, Monday 09:00 → following Monday 09:00 (in the on-call's local time zone).
- **Tiers:** Primary + Secondary. Primary takes the page; Secondary covers Primary's life events (sleep, family, conferences).
- **Roster:** every engineer with production write access. The default rotation is alphabetic, but the team adjusts for new joiners (no on-call for the first 60 days), parental leave, and travel.
- **Fair distribution:** the goal is to share weeks evenly across a quarter. If someone covers a colleague's week, the colleague returns a week within the next quarter.
- **Holiday coverage:** the on-call rotation does not stop. If your scheduled week includes a public holiday, you can swap with a colleague — coordinate ahead.

Schedule is maintained in PagerDuty (or equivalent). Source-of-truth ICS feed at `https://pagerduty.example.com/rotation/ec.ics`.

---

## What "being on call" means

- Carry a phone capable of receiving the page (sound + vibration enabled, do-not-disturb override for the on-call number).
- Be reachable within **5 minutes** of a page.
- Have a laptop with VPN credentials and admin access reachable within **15 minutes** of a page.
- No alcohol-impaired or otherwise impaired on duty.
- Pages take precedence over meetings, deep work, and (within reason) family commitments — but if you cannot respond, hand off to Secondary immediately.

Sev 3 pages do not actually page outside business hours — they create tickets the on-call reviews next business day.

---

## Handoff checklist

Every Monday at 09:00 the outgoing Primary holds a 15-minute handoff with the incoming Primary. Use this checklist:

- [ ] Any open incidents from the past week? Status and owner.
- [ ] Any recent deploys that warrant extra monitoring?
- [ ] Any known-issue noise on alerts (tune or suppress before handing over)?
- [ ] Any customer-success escalations that may produce pages?
- [ ] Any infra changes scheduled (DB upgrade, certificate rotation) during the upcoming week?
- [ ] Any compliance / audit work the incoming Primary should be aware of?
- [ ] Incoming Primary's contact details up to date in PagerDuty.
- [ ] Outgoing Primary marks their week's notes in `docs/on-call-logbook.md`.

---

## Tools and access

The on-call needs the following before their first shift:

- PagerDuty (or equivalent) account with the EnterpriseCore rotation assigned.
- VPN or bastion access to production network.
- `kubectl` / `aws` / `gcloud` CLI configured with on-call role assumed (read-write to the runtime, read-only to billing).
- Read access to the centralised log store (Loki / Splunk / Datadog).
- Read-write to Prometheus / Grafana for setting silences and acks.
- Read access to the customer DB (with audit logging).
- Admin token for the EnterpriseCore admin API (rotated weekly).
- Access to the customer status page (Statuspage.io or equivalent).
- Slack access to `#ec-incidents`, `#ec-ops`, `#ec-security`.
- Phone number on the company emergency contact list.

The on-call should verify all of the above on Day 1 of the week by:

1. Running `kubectl get pods -n ec-prod` (lists pods).
2. Opening Grafana → EnterpriseCore Overview (loads).
3. Posting a "Hello on-call week" message in `#ec-ops`.

---

## Escalation tree

The on-call's job is to fix what they can and escalate what they can't.

Escalate when:

- The page is in a system you've never touched.
- Mitigation requires changes outside your authorisation (financial credits, security disclosure).
- You've been working for >2 hours and the issue is not converging — fatigue makes things worse.
- The customer is a strategic / enterprise account requiring executive comms.

Escalation order:

1. **Secondary on-call** — for technical depth or coverage.
2. **Subject-matter engineer** — for a specific subsystem. Maintain a `subject-matter` table in `docs/on-call-logbook.md`.
3. **Engineering manager on duty** — for resourcing decisions, P0 prioritisation.
4. **VP Engineering** — for cross-team coordination, multi-day incidents.
5. **CTO** — for board-level / customer-facing executive escalation.
6. **CEO** — for severe customer impact, media risk, or legal exposure.

Internally-tracked phone numbers and Slack DMs in a sealed envelope in the password manager. The on-call confirms reachability at week start.

For security incidents the escalation is:

1. Security lead on-call (separate rotation).
2. CISO.
3. Outside counsel (if confirmed unauthorised access).

---

## After a page

Within 24 hours of a Sev 1 / Sev 2 page:

- File the incident document under `docs/postmortems/draft/`.
- Capture timeline, mitigation steps taken, and outstanding questions.
- Schedule the postmortem meeting.

Within 5 business days:

- Publish the postmortem.
- Open action-item tickets with owners and due dates.

---

## On-call compensation policy (placeholder)

This section is intentionally a placeholder — every organisation tailors compensation to their geography, employment structure, and cultural norms. Suggested elements to define:

- Flat weekly stipend for being on call (whether or not paged).
- Per-incident-hour additional compensation for off-hours work.
- Comp days for sustained off-hours work in a quarter (e.g., one comp day per 8 hours of off-hours incident time).
- Floor on the number of times you can be paged before automatic relief.
- Procedure for opt-out (medical, family, etc.).

This must be HR-approved and documented in the employee handbook before the rotation goes live.

---

## Wellbeing

- The on-call's calendar should be cleared of non-essential meetings.
- Block 09:30-10:00 each day for triage / followups.
- If you don't sleep through the night, take a half-day off the next morning — productive engineers need rest, exhausted engineers cause incidents.
- Quarterly review of pages per rotation — if any one person is taking outsized pages, redistribute load or fix the alerts.
