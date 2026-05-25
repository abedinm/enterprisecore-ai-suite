# Runbook — Webhook delivery failing

## Symptoms

- Customer complaint: "We're not getting webhook events for X."
- Admin dashboard: `Webhooks → Delivery` shows >5% failure rate for a tenant.
- `ec_webhook_delivery_failures_total` metric climbing.
- Log line: `webhook_dispatcher: delivery failed url=... status=...`.

## Severity

- **Sev 2** if delivery to one tenant or one URL is failing.
- **Sev 1** if delivery is failing across multiple tenants AND data is being dropped (no retry).

## Immediate mitigation

1. Inspect the dead-letter queue for the affected tenant:

   ```bash
   curl -fsS -H "Authorization: Bearer $ADMIN_TOKEN" \
     "https://app.example.com/api/v1/admin/webhooks/dlq?tenant_id=$TENANT_ID" | jq .
   ```

2. Confirm the destination URL is reachable from the backend:

   ```bash
   curl -v -X POST "$WEBHOOK_URL" \
     -H "Content-Type: application/json" \
     -d '{"ping":true}' --max-time 5
   ```

3. If the URL is permanently dead, ask the customer for a new URL or pause delivery:

   ```bash
   curl -X PATCH -H "Authorization: Bearer $ADMIN_TOKEN" \
     "https://app.example.com/api/v1/admin/webhooks/$WEBHOOK_ID" \
     -d '{"active": false}'
   ```

4. If the URL is reachable but our payload is rejected (400/422), grab a sample failed payload and the receiver's response from the DLQ for the customer.

5. Replay successful payloads from the DLQ after the receiver is fixed:

   ```bash
   curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
     "https://app.example.com/api/v1/admin/webhooks/dlq/replay?tenant_id=$TENANT_ID"
   ```

## Root cause investigation

Bucket by failure type:

```promql
sum by (status_class) (rate(ec_webhook_delivery_failures_total[15m]))
```

- `4xx` — receiver-side problem (auth, validation, wrong content-type). Usually customer fix.
- `5xx` — receiver outage. Wait + retry (the dispatcher already does this with exponential backoff).
- `timeout` — receiver slow. Check whether `WEBHOOK_TIMEOUT_SECONDS` (default 10) is appropriate.
- `dns` — receiver host unresolvable. Customer changed DNS.
- `tls` — certificate expired / chain broken. Customer fix.

Inspect a single failed delivery:

```bash
curl -fsS -H "Authorization: Bearer $ADMIN_TOKEN" \
  "https://app.example.com/api/v1/admin/webhooks/deliveries/$DELIVERY_ID" | jq .
```

## Permanent fix

- For chronic 4xx receivers, send a customer email after N consecutive failures using `app/services/email_service.py`.
- Pause a webhook after 100 consecutive failures and notify the tenant admin (existing logic in `webhook_dispatcher.py`; verify `MAX_CONSECUTIVE_FAILURES` env var).
- Improve the developer docs in `docs/WEBHOOKS.md` to clarify payload contract.

## Postmortem checklist

- [ ] Was data lost or only delayed?
- [ ] Were customers notified proactively?
- [ ] Did the auto-pause logic trigger as expected?
- [ ] Are the retry / backoff parameters appropriate?
