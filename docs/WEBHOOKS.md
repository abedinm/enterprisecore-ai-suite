# Webhooks

EnterpriseCore can POST signed events to your endpoint whenever something
happens inside the suite. Use it to:

- Sync CRM leads to your data warehouse
- Notify Slack when a deal moves to `won`
- Kick off a zap when an invoice is paid
- Trigger your own downstream automation

This document covers the event catalog, the subscription model, signature
verification (with Python + Node + curl examples), the retry policy, and
best practices for receivers.

## Event catalog

Subscribe to specific event types — or `*` for every event — when you
create a subscription. Wildcards like `crm.*` work too (fnmatch-style).

`GET /api/v1/webhooks/event-types` returns the live catalog as JSON. The
table below is the stable spec.

| Event type                       | When it fires                                              |
| -------------------------------- | ---------------------------------------------------------- |
| `crm.lead.created`               | New sales lead inserted                                    |
| `crm.lead.updated`               | Existing lead patched                                      |
| `crm.deal.won`                   | Deal stage transitions to `won`                            |
| `crm.deal.lost`                  | Deal stage transitions to `lost`                           |
| `finance.invoice.created`        | Invoice row created                                        |
| `finance.invoice.paid`           | Invoice transitions to `paid`                              |
| `finance.invoice.overdue`        | Invoice flagged `overdue`                                  |
| `hr.employee.created`            | Employee record created                                    |
| `hr.employee.terminated`         | Employee marked terminated                                 |
| `hr.leave.approved`              | Leave request approved by manager                          |
| `projects.project.created`       | New project                                                |
| `projects.task.completed`        | Task status → `done`                                       |
| `webchat.conversation.created`   | New public webchat conversation started                    |
| `webchat.contact_linked`         | Conversation linked to a CRM contact                       |
| `marketing.post.published`       | Blog / marketing post published                            |
| `marketing.template.applied`     | A marketing site template was applied                      |
| `construction.project.created`   | New construction project                                   |
| `construction.risk.created`      | Risk register entry created                                |
| `construction.variation.approved`| Variation order approved                                   |
| `knowledge.document.ingested`    | Knowledge-base document finished ingesting                 |
| `tenant.created`                 | A new tenant signed up                                     |
| `tenant.plan.changed`            | Tenant's billing plan was changed                          |
| `tenant.cancelled`               | Tenant cancelled their subscription                        |
| `user.invited`                   | User invited to a tenant                                   |
| `user.activated`                 | User accepted invite + activated their account             |
| `user.deactivated`               | User deactivated (covers GDPR erasure)                     |
| `ai.spend.threshold_crossed`     | AI monthly spend crossed 50/80/100% of cap                 |
| `billing.subscription.upgraded`  | Subscription upgraded to a higher plan                     |
| `billing.payment.failed`         | Payment attempt failed                                     |
| `webhook.test`                   | Fired by `POST /webhooks/subscriptions/{id}/test`          |

## Subscription model

Create a subscription via `POST /api/v1/webhooks/subscriptions`:

```http
POST /api/v1/webhooks/subscriptions
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "name": "Slack — deal won notifier",
  "url": "https://hooks.example.com/ec/slack",
  "event_types": ["crm.deal.won", "crm.deal.lost"]
}
```

Response (returns the secret exactly ONCE):

```json
{
  "id": "01HVK...",
  "name": "Slack — deal won notifier",
  "url": "https://hooks.example.com/ec/slack",
  "event_types": ["crm.deal.won", "crm.deal.lost"],
  "is_active": true,
  "secret": "store-this-it-will-not-be-shown-again"
}
```

To rotate the secret later: `PATCH /webhooks/subscriptions/{id}` with
`{"rotate_secret": true}`. The new secret is returned once.

## Delivery format

Every webhook POST has the following shape:

```http
POST https://hooks.example.com/ec/slack HTTP/1.1
Content-Type: application/json
User-Agent: EnterpriseCore-Webhook/1.0
X-EC-Event-Id: 01HVKAB...
X-EC-Event-Type: crm.deal.won
X-EC-Signature: sha256=<hex hmac>
X-EC-Timestamp: 2026-05-23T10:42:31.123456+00:00
X-EC-Attempt: 1

{
  "id": "01HVKAB...",
  "type": "crm.deal.won",
  "tenant_id": "01HVK...",
  "user_id": "01HVK...",
  "occurred_at": "2026-05-23T10:42:31.123456+00:00",
  "payload": {
    "deal_id": "01HVK...",
    "title": "Riverside — fit-out phase 2",
    "value": "180000.00"
  }
}
```

The `payload` object is event-specific. Subscribe to a real event in a
sandbox tenant and inspect the delivery to learn the exact shape.

## Signature verification

Sign your way out of replay attacks: hash the raw body bytes with
`HMAC-SHA256` using the secret you stored at subscription time, then
compare against `X-EC-Signature`.

### Python (Flask)

```python
import hmac, hashlib
from flask import Flask, request, abort

SECRET = b"store-this-it-will-not-be-shown-again"

app = Flask(__name__)

@app.post("/ec/webhook")
def handle():
    sig = request.headers.get("X-EC-Signature", "").removeprefix("sha256=")
    expected = hmac.new(SECRET, request.get_data(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        abort(401)
    # ...your work here...
    return ("", 200)
```

### Node (Express)

```javascript
import express from "express";
import crypto from "crypto";

const SECRET = "store-this-it-will-not-be-shown-again";
const app = express();
app.use(express.raw({ type: "application/json" }));  // RAW body required

app.post("/ec/webhook", (req, res) => {
  const sig = (req.headers["x-ec-signature"] || "").replace("sha256=", "");
  const expected = crypto.createHmac("sha256", SECRET)
                         .update(req.body)
                         .digest("hex");
  if (!crypto.timingSafeEqual(Buffer.from(sig, "hex"),
                              Buffer.from(expected, "hex"))) {
    return res.status(401).end();
  }
  // ...your work here...
  res.status(200).end();
});

app.listen(3000);
```

### Curl (one-off verification)

```bash
BODY='{"id":"...","type":"crm.deal.won",...}'
SECRET="store-this-it-will-not-be-shown-again"
echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -hex
```

The hex output must match `X-EC-Signature` (minus the `sha256=` prefix).

## Retry policy

We retry on any non-2xx response and on transport errors (DNS, TLS,
timeouts). Schedule:

| Attempt | Delay since previous |
| ------- | -------------------- |
| 1       | immediate            |
| 2       | 1 minute             |
| 3       | 5 minutes            |
| 4       | 30 minutes           |
| 5       | 2 hours              |
| 6       | 12 hours             |
| 7       | 24 hours             |

After the 7th attempt fails, the subscription is **paused for 24 hours**
(`disabled_until` is set). Once 24 consecutive failures have accumulated,
the subscription is marked `is_active=false` and an email goes to the
tenant admin.

Re-enabling a paused subscription (via `PATCH ... {"is_active": true}`)
clears the counter so the next event fires immediately.

`POST /webhooks/deliveries/{id}/retry` re-fires a single delivery — useful
when you know your receiver is back up + you don't want to wait for the
next scheduled retry.

## Best practices for receivers

1. **Return 200 fast.** We use a 10-second timeout. If your handler takes
   longer than that we count it as a failure and retry. Enqueue the work
   instead of doing it inline.
2. **Verify the signature.** A POST without a valid signature is either
   spoofed or coming from a sender that doesn't know your secret. Reject
   it with 401.
3. **Treat events as idempotent.** Retries can deliver the same `event_id`
   more than once. Store seen event ids and skip duplicates.
4. **Process in `occurred_at` order if your logic depends on ordering.**
   The retry schedule can deliver attempt 3 of one event after attempt 1
   of a later one.
5. **Plan for partial delivery.** If you operate multiple receivers, treat
   each event as independent — one failing doesn't roll back the others.

## Observability

`GET /webhooks/subscriptions/{id}/deliveries` returns the most recent 50
delivery attempts with status, latency, and the first 500 chars of the
response body — invaluable when chasing down a misbehaving receiver.
