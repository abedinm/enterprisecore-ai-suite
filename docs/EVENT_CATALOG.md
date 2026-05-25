# Event catalog

EnterpriseCore publishes a canonical set of events on every state change a
subscriber would plausibly care about. Events power three things:

1. **Outbound webhooks.** External systems (Zapier, Slack, the customer's
   warehouse) subscribe to event types via
   `POST /api/v1/webhooks/subscriptions`.
2. **Internal in-process handlers.** Modules call
   `event_bus.subscribe()` for synchronous reactions (search-index
   rebuild, AI spend thresholds → notifications).
3. **Cross-process fanout.** When `REDIS_URL` is set, events are also
   pushed onto a per-tenant Redis stream so external workers can drain
   them.

This catalog is the **stable spec** — event names and payload shapes are
contract for integrators. New events append to the list; existing events
keep their shape forever (additive-only).

For the high-level subscription API, see [WEBHOOKS.md](WEBHOOKS.md). For
signature verification code in six languages, see
[WEBHOOK_VERIFICATION_EXAMPLES.md](WEBHOOK_VERIFICATION_EXAMPLES.md).

## Envelope

Every event has the same outer envelope. The `payload` field is the only
piece that varies.

```json
{
  "id": "01HXK7AYJ0M9V2N1ZS6Q3D4F5G",
  "type": "crm.deal.won",
  "tenant_id": "01HV...",
  "user_id": "01HV...",
  "occurred_at": "2026-05-23T09:14:21.117482+00:00",
  "payload": { /* event-specific shape — see below */ }
}
```

| Field         | Type     | Notes                                                    |
| ------------- | -------- | -------------------------------------------------------- |
| `id`          | ULID     | Idempotency key. Receivers MUST dedupe by this.          |
| `type`        | string   | One of the event types below.                            |
| `tenant_id`   | string   | Scopes the event to a single tenant. Null only for       |
|               |          | tenant-lifecycle events that fire before tenant exists.  |
| `user_id`     | string   | The user that triggered the change; null for system.    |
| `occurred_at` | ISO 8601 | UTC. Use for replay protection.                          |
| `payload`     | object   | Event-specific. JSON object; never a primitive or array. |

## CRM

### `crm.lead.created`
Fires immediately after a new sales lead row is inserted.

```json
{
  "lead_id": "01HW...",
  "name": "Sarah Chen",
  "email": "sarah@acme.co",
  "company": "Acme Co",
  "source": "website",
  "assigned_to_id": null
}
```
Default subscribers: Slack connector (channel `#sales-new-leads`), Zapier.

### `crm.lead.updated`
Fires when any lead field is patched. The payload includes the full
post-update lead row plus a `changed` map keyed by field name.

```json
{
  "lead_id": "01HW...",
  "name": "Sarah Chen",
  "company": "Acme Inc",
  "changed": {
    "company": { "from": "Acme Co", "to": "Acme Inc" }
  }
}
```

### `crm.deal.won`
Fires when a deal transitions to the `won` stage.

```json
{
  "deal_id": "01HW...",
  "lead_id": "01HW...",
  "amount_cents": 4500000,
  "currency": "USD",
  "stage": "won",
  "closed_at": "2026-05-23T09:14:21.117482+00:00",
  "customer_name": "Acme Inc"
}
```
Default subscribers: Slack `#deals-won`, billing service (offers
upsell), data warehouse webhook.

### `crm.deal.lost`
Same payload shape as `crm.deal.won` plus a `lost_reason` string.

## Finance

### `finance.invoice.created`
```json
{
  "invoice_id": "01HW...",
  "customer_id": "01HW...",
  "amount_cents": 120000,
  "currency": "USD",
  "issued_at": "2026-05-23T00:00:00+00:00",
  "due_at": "2026-06-22T00:00:00+00:00",
  "line_items_count": 3
}
```

### `finance.invoice.paid`
```json
{
  "invoice_id": "01HW...",
  "amount_cents": 120000,
  "currency": "USD",
  "paid_at": "2026-05-25T12:01:33+00:00",
  "payment_method": "stripe_card"
}
```
Default subscribers: data warehouse, Slack `#finance-cash`.

### `finance.invoice.overdue`
Fires when a daily housekeeping job marks an unpaid invoice past its due
date.

```json
{
  "invoice_id": "01HW...",
  "amount_cents": 120000,
  "currency": "USD",
  "due_at": "2026-04-22T00:00:00+00:00",
  "days_overdue": 31
}
```

## HR

### `hr.employee.created`
```json
{
  "employee_id": "01HW...",
  "name": "Marcus Liu",
  "email": "marcus@your-org.com",
  "title": "Senior Engineer",
  "department": "Engineering",
  "starts_on": "2026-06-01"
}
```
Default subscribers: Google Workspace (provision Gmail), Slack
(`#welcomes`), SCIM (sync to IdP).

### `hr.employee.terminated`
```json
{
  "employee_id": "01HW...",
  "terminated_at": "2026-05-23T17:00:00+00:00",
  "reason": "voluntary"
}
```
Default subscribers: Google Workspace (suspend account), SCIM
(deprovision), DocuSign (revoke pending envelopes).

### `hr.leave.approved`
```json
{
  "leave_id": "01HW...",
  "employee_id": "01HW...",
  "starts_on": "2026-07-01",
  "ends_on": "2026-07-12",
  "kind": "annual"
}
```

## Projects + Tasks

### `projects.project.created`
```json
{
  "project_id": "01HW...",
  "name": "Q3 Website refresh",
  "owner_id": "01HW...",
  "starts_on": "2026-07-01",
  "ends_on": "2026-09-30"
}
```

### `projects.task.completed`
```json
{
  "task_id": "01HW...",
  "project_id": "01HW...",
  "completed_by_id": "01HW...",
  "completed_at": "2026-05-23T15:20:00+00:00"
}
```

## Webchat

### `webchat.conversation.created`
Fires when a visitor opens a new conversation through the embeddable
widget.

```json
{
  "conversation_id": "01HW...",
  "bot_id": "01HW...",
  "visitor_ip_hash": "8e2a...",
  "visitor_user_agent": "Mozilla/5.0...",
  "page_url": "https://acme.co/pricing"
}
```

### `webchat.contact_linked`
Fires when a conversation is matched to a CRM contact (via email
collection or a manual link).

```json
{
  "conversation_id": "01HW...",
  "contact_id": "01HW...",
  "matched_by": "email"
}
```

## Marketing

### `marketing.post.published`
```json
{
  "post_id": "01HW...",
  "slug": "launching-our-2026-roadmap",
  "title": "Launching our 2026 roadmap",
  "published_at": "2026-05-23T13:00:00+00:00",
  "author_id": "01HW..."
}
```
Default subscribers: search index rebuild, Slack `#marketing-shipped`.

### `marketing.template.applied`
Fires when an operator applies a built-in marketing site template.

```json
{
  "site_id": "01HW...",
  "template_id": "saas-launch-v2",
  "applied_by_id": "01HW..."
}
```

## Construction

### `construction.project.created`
```json
{
  "project_id": "01HW...",
  "code": "PROJ-2026-014",
  "name": "Riverside Tower Phase 2",
  "client_id": "01HW...",
  "contract_value_cents": 1850000000,
  "currency": "USD"
}
```

### `construction.risk.created`
```json
{
  "risk_id": "01HW...",
  "project_id": "01HW...",
  "title": "Steel delivery slip — Tier-3 supplier",
  "severity": "high",
  "owner_id": "01HW..."
}
```

### `construction.variation.approved`
```json
{
  "variation_id": "01HW...",
  "project_id": "01HW...",
  "code": "VO-014-007",
  "amount_cents": 4200000,
  "approved_by_id": "01HW..."
}
```

## Knowledge

### `knowledge.document.ingested`
Fires when a knowledge-base document finishes its embedding + chunking
pipeline.

```json
{
  "document_id": "01HW...",
  "title": "Onboarding playbook",
  "source_path": "kb/onboarding/playbook.md",
  "chunk_count": 42,
  "tokens": 18342
}
```

## Tenant lifecycle

### `tenant.created`
Fires on tenant signup. Note this event's `tenant_id` is set even though
it's the moment of creation (the event is published from inside the
post-create transaction).

```json
{
  "tenant_id": "01HW...",
  "name": "Acme Inc",
  "plan": "starter",
  "owner_email": "founder@acme.co"
}
```

### `tenant.plan.changed`
```json
{
  "tenant_id": "01HW...",
  "from_plan": "starter",
  "to_plan": "growth",
  "effective_at": "2026-05-23T00:00:00+00:00"
}
```

### `tenant.cancelled`
```json
{
  "tenant_id": "01HW...",
  "cancelled_at": "2026-05-23T18:30:00+00:00",
  "reason": "self_serve_cancel"
}
```

## User lifecycle

### `user.invited`
```json
{
  "user_id": "01HW...",
  "email": "newhire@your-org.com",
  "invited_by_id": "01HW...",
  "role": "member"
}
```

### `user.activated`
```json
{
  "user_id": "01HW...",
  "activated_at": "2026-05-23T14:11:02+00:00"
}
```

### `user.deactivated`
Fires for both manual deactivation and GDPR erasure.

```json
{
  "user_id": "01HW...",
  "deactivated_at": "2026-05-23T14:11:02+00:00",
  "kind": "gdpr_erase"
}
```

## AI

### `ai.spend.threshold_crossed`
Fires when monthly AI spend crosses 50%, 80%, or 100% of the tenant's
cap. The same threshold is not refired in the same calendar month.

```json
{
  "threshold_pct": 80,
  "spend_cents": 8000,
  "cap_cents": 10000,
  "currency": "USD",
  "month": "2026-05"
}
```

## Billing

### `billing.subscription.upgraded`
```json
{
  "subscription_id": "01HW...",
  "from_plan": "starter",
  "to_plan": "growth",
  "mrr_delta_cents": 19900,
  "effective_at": "2026-05-23T00:00:00+00:00"
}
```

### `billing.payment.failed`
```json
{
  "invoice_id": "01HW...",
  "amount_cents": 19900,
  "currency": "USD",
  "failure_code": "card_declined",
  "retry_at": "2026-05-26T00:00:00+00:00"
}
```

## Internal

### `webhook.test`
Fired by `POST /webhooks/subscriptions/{id}/test` so customers can verify
their endpoint without waiting for real activity.

```json
{
  "sent_by_id": "01HW...",
  "test": true
}
```

## How to subscribe via curl

Create a subscription:

```bash
curl -X POST https://<host>/api/v1/webhooks/subscriptions \
  -H "Authorization: Bearer $EC_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Slack — deals won",
    "url":  "https://hooks.slack.com/services/T000/B000/XXXX",
    "event_types": ["crm.deal.won"]
  }'
```

The response carries the signing secret **once**:

```json
{
  "id": "01HVK...",
  "secret": "wsk_3f4c...long-random...",
  "url": "https://hooks.slack.com/services/T000/B000/XXXX",
  "event_types": ["crm.deal.won"],
  "is_active": true
}
```

Verify the next incoming POST in Python:

```python
import hmac, hashlib

def verify(raw_body: bytes, header_sig: str, secret: bytes) -> bool:
    expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", header_sig)
```

For Node.js / PHP / Ruby / Go / Java equivalents see
[WEBHOOK_VERIFICATION_EXAMPLES.md](WEBHOOK_VERIFICATION_EXAMPLES.md).

## Wildcards

`event_types` accepts fnmatch-style wildcards:

- `crm.*` — every CRM event.
- `*.created` — every entity-creation event across modules.
- `*` — fire on every event (use sparingly; you'll receive a lot).

The catalog is also reachable live at
`GET /api/v1/webhooks/event-types`, which always reflects the running
build.
