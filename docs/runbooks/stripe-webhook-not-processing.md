# Runbook — Stripe webhook not processing

## Symptoms

- Customer reports a paid invoice but the tenant is still showing as `past_due` / `trialing`.
- `ec_stripe_webhook_processed_total` rate near zero.
- Logs: `stripe.signature_verification_failed` OR `stripe.webhook.unhandled_event`.
- Stripe Dashboard → Developers → Webhooks shows red exclamation on the endpoint.

## Severity

- **Sev 1** — customer billing state is wrong. Revenue impact. Page billing / finance lead.

## Immediate mitigation

1. Open Stripe Dashboard → Developers → Webhooks → your endpoint. Inspect the most recent failed delivery.

2. If signature verification is failing, the secret is wrong. Pull the secret from Stripe and update:

   ```bash
   STRIPE_WEBHOOK_SECRET=whsec_... aws ssm put-parameter \
     --name /ec/prod/stripe/webhook_secret --type SecureString --overwrite
   sudo systemctl restart ec-backend
   ```

3. Replay failed events from Stripe:

   - Stripe Dashboard → Developers → Events → filter Failed → click each event → "Resend webhook."
   - Or use Stripe CLI: `stripe events resend evt_...`.

4. For each affected customer, reconcile manually if replay does not catch up:

   ```bash
   curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
     "https://app.example.com/api/v1/admin/billing/reconcile" \
     -d '{"customer_id": "cus_..."}'
   ```

## Root cause investigation

- **Wrong secret** — most common. Happens after `stripe trigger` testing in production.
- **Signature timestamp drift** — server clock skew >5 minutes. Check `timedatectl status`.
- **New event type** — Stripe added an event your handler does not recognise. Look at the Stripe event payload for the failure.
- **Deployment in progress** — events delivered to a node that's draining. Stripe will retry; usually self-heals within minutes.
- **Database write failure** — log will show the underlying error. See `database-connection-pool-exhausted.md` if that's the cause.

Query recent stripe events:

```bash
psql -c "SELECT id, type, processed_at, error
         FROM stripe_events
         ORDER BY received_at DESC LIMIT 50;"
```

## Permanent fix

- Lock down who can run `stripe trigger`/`stripe listen` against production.
- Add a `StripeEventBacklog` alert: `time() - max(stripe_last_event_processed_at) > 600`.
- Move the webhook handler to the job queue (already done as of Wave 4) so retries are idempotent and persistent.
- Document idempotency keys for new event types.

## Postmortem checklist

- [ ] How many customers had incorrect billing state?
- [ ] Were any subscriptions cancelled or charged incorrectly as a result?
- [ ] Was reconciliation needed or did replay suffice?
- [ ] Are alerts tight enough to detect within 5 minutes?
