# Billing & Subscriptions

EnterpriseCore AI Suite uses Stripe for hosted subscription billing. The
integration is intentionally optional: every Stripe call has a graceful
fallback, so self-host customers who want to bill outside Stripe ("self-
managed mode") get a working app with no Stripe credentials configured.

This document covers the pricing model, environment variables, Stripe
Dashboard setup, the upgrade journey, trial mechanics, and how
self-managed mode works.

---

## 1. The pricing model

Three subscription SKUs, all available monthly or yearly.

| Plan        | Includes                           | Base seats | Monthly | Yearly  |
|-------------|------------------------------------|-----------:|--------:|--------:|
| Core        | Every always-on module + webchat   | 5          | $99     | $990    |
| +EDU        | Core + academic module pack        | 25         | $299    | $2,990  |
| +Verticals  | Core + extra industry templates    | 10         | $199    | $1,990  |

Yearly is roughly two months free. Every plan ships with included
allowances; the customer is charged a metered overage on top when they
exceed them.

### Per-seat overage

Once the tenant's active-user count exceeds the plan's base seats, each
additional seat is billed at **$12 / seat / month**. Yearly tenants are
billed pro-rated at the equivalent annualized rate.

### AI metered usage

Cloud AI (Anthropic, OpenAI) is metered. Ollama (local, on-device
inference) is free and never counted. Each plan ships with a monthly
cloud-AI allowance:

| Plan        | Included cloud-AI / month |
|-------------|--------------------------:|
| Evaluation  | $5                        |
| Core        | $50                       |
| +EDU        | $150                      |
| +Verticals  | $100                      |

Spend beyond the allowance is reported to Stripe at the end of each
billing period at **$0.50 per 1,000 tokens** and added to the next
invoice.

The current period's spend is visible to admins at
`GET /api/v1/billing/usage`.

---

## 2. Configuration

Stripe is configured exclusively through environment variables. Set
these on the backend process (FastAPI app), not on the desktop client.

| Env var                          | Required?         | Description                                                                                  |
|----------------------------------|-------------------|----------------------------------------------------------------------------------------------|
| `STRIPE_SECRET_KEY`              | If using Stripe   | Secret key from your Stripe Dashboard (`sk_test_…` for test mode, `sk_live_…` for live).      |
| `STRIPE_WEBHOOK_SECRET`          | If using Stripe   | Signing secret from the webhook endpoint you create in Stripe (`whsec_…`).                    |
| `STRIPE_PRICE_CORE_MONTHLY`      | Recommended       | Stripe Price ID for the Core monthly subscription (`price_…`).                                |
| `STRIPE_PRICE_CORE_YEARLY`       | Recommended       | Stripe Price ID for the Core yearly subscription.                                             |
| `STRIPE_PRICE_EDU_MONTHLY`       | Recommended       | Stripe Price ID for the +EDU monthly subscription.                                            |
| `STRIPE_PRICE_EDU_YEARLY`        | Recommended       | Stripe Price ID for the +EDU yearly subscription.                                             |
| `STRIPE_PRICE_VERTICALS_MONTHLY` | Recommended       | Stripe Price ID for the +Verticals monthly subscription.                                      |
| `STRIPE_PRICE_VERTICALS_YEARLY`  | Recommended       | Stripe Price ID for the +Verticals yearly subscription.                                       |
| `STRIPE_SUCCESS_URL`             | Optional          | Default success URL for Checkout (override per request via the `success_url` field).          |
| `STRIPE_CANCEL_URL`              | Optional          | Default cancel URL for Checkout.                                                              |
| `STRIPE_PORTAL_RETURN_URL`       | Optional          | Default return URL for the Stripe Customer Portal.                                            |
| `BILLING_SELF_MANAGED_URL`       | Optional          | Docs URL the API returns instead of a Checkout URL when Stripe is not configured.             |

When `STRIPE_SECRET_KEY` is unset, **every** Stripe call is replaced by
a soft-fail return value — no crashes, no exceptions thrown into the
calling endpoint. See section 5.

---

## 3. Stripe Dashboard setup

1. **Products + Prices.** In Products, create three products (one per
   SKU). Inside each product, add **two recurring prices**: one with a
   monthly interval, one with a yearly interval. Note the IDs (they
   start with `price_…`) and copy them into the env vars above.

2. **Metadata.** On each price's metadata, set `plan` to one of
   `core`, `edu`, or `verticals`. The webhook handler reads this field
   when reconciling a subscription back to a local `TenantSubscription`
   row, so it matters that it's exactly the SKU slug.

3. **Optional: metered prices.** For per-seat overage and AI overage,
   add a usage-metered price to each product and tag its metadata with
   `meter_key=ai_paid_tokens` (or another meter key). The
   `report_metered_usage` job will pick those up automatically.

4. **Webhook endpoint.** Under Developers → Webhooks, click "Add
   endpoint" and point it at `https://<your-app>/stripe/webhook` (NOT
   `/api/v1/stripe/webhook`). Subscribe to at least:

   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `customer.subscription.trial_will_end`
   - `invoice.paid`
   - `invoice.payment_failed`

   Copy the signing secret (`whsec_…`) into `STRIPE_WEBHOOK_SECRET`.

5. **Customer Portal.** Under Settings → Billing → Customer portal,
   turn on the features you want to expose (update card, cancel
   subscription, view invoices, change plan). The backend hands users a
   one-time portal session URL via `POST /api/v1/billing/portal`.

---

## 4. The customer upgrade journey

From the customer's perspective:

1. Sign up. New tenants land on the **evaluation** plan with a 14-day
   trial of every feature.
2. Open **Settings → Billing**. The UI lists plans by calling
   `GET /api/v1/billing/plans`.
3. Click "Upgrade to Core". The UI calls
   `POST /api/v1/billing/checkout` with `{plan: "core", interval: "month"}`
   and receives a Stripe Checkout URL. The browser redirects there.
4. Customer enters card details. Stripe handles 3DS / SCA and any
   regional payment-method UX. On success, Stripe redirects to
   `STRIPE_SUCCESS_URL`.
5. Stripe fires `customer.subscription.created`. The webhook handler
   creates a `TenantSubscription` row, sets `tenant.plan = "core"` and
   `tenant.status = "active"`. The next request from the customer sees
   the new SKU's features unlocked.
6. The customer can self-service from here: update card, view
   invoices, change plan, cancel. **Settings → Billing → Manage**
   calls `POST /api/v1/billing/portal` and redirects to the Stripe
   Customer Portal.

To cancel without going through the portal, an admin can hit
`POST /api/v1/billing/cancel`. Cancellation is scheduled at the end of
the current period; `POST /api/v1/billing/resume` undoes it as long as
the period hasn't rolled.

---

## 5. Self-managed mode

When `STRIPE_SECRET_KEY` is **not** set, the app runs in **self-managed
mode**. This is the default for:

- Local dev / CI.
- Self-host customers who manage billing outside Stripe (purchase orders,
  wire transfers, internal procurement workflows).

Behavioural differences:

| Surface                            | Self-managed                                                              |
|------------------------------------|---------------------------------------------------------------------------|
| `GET /billing/plans`               | Returns the same catalog with `self_managed: true`.                       |
| `POST /billing/checkout`           | Returns `BILLING_SELF_MANAGED_URL` (default: a docs page) instead of Stripe Checkout. |
| `POST /billing/portal`             | Same — returns the docs URL.                                              |
| `POST /billing/cancel` / `resume`  | Mutates the local `TenantSubscription` row only; never calls Stripe.      |
| `GET /billing/invoices`            | Returns `{invoices: [], self_managed: true}`.                             |
| `POST /stripe/webhook`             | Skips signature verification; events from internal forwarders are accepted as plain JSON and processed normally. |

In all cases the local audit trail (`BillingEvent` table) is still
written and the `TenantSubscription` row still reflects the plan, so
the rest of the app gates features identically.

To switch a self-managed customer to a Stripe-billed plan, the operator
manually creates a `TenantSubscription` row for them via the admin tools
(or directly in SQL) and the app picks up the SKU on the next request.

---

## 6. Trial mechanics

Trials are 14 days by default. The signup flow sets
`tenant.trial_ends_at = now() + 14 days` and the tenant runs on the
`evaluation` plan with every feature unlocked.

The `expire_trials` housekeeping job runs daily and transitions any
tenant past `trial_ends_at` (and still on `evaluation`) to status
`trial_expired`. The frontend reads `tenant.status` on boot and shows
a "Trial ended" banner with an upgrade CTA when the value is
`trial_expired`.

The webhook handler for Stripe's `customer.subscription.trial_will_end`
event sends the tenant admin a reminder email 3 days before the
subscription's `trial_end` timestamp. Email delivery is best-effort: if
`app.services.email` is wired up it goes out as a real email; otherwise
the reminder is logged so the operator can act on it manually.

---

## 7. Data model

Three tables, all tenant-scoped:

- **`tenant_subscriptions`** — one active sub per tenant. Tracks
  `plan`, `status`, `seat_count`, `seat_quota`, `overage_seats`,
  `current_period_*`, `amount_per_period`, the Stripe `subscription_id`
  and `customer_id`.
- **`billing_events`** — append-only audit. Every webhook delivery
  writes one row, idempotent on `stripe_event_id` via a UNIQUE
  constraint, so a duplicate Stripe delivery is silently absorbed.
- **`usage_meters`** — per-tenant, per-meter-key, per-period quantity.
  Currently the only meter is `ai_paid_tokens`; the same shape extends
  to `storage_gb`, `api_calls`, etc.

The migration that creates them is `alembic/versions/0015_billing.py`.

---

## 8. Endpoint reference

All routes are auth-required and tenant-scoped by the ORM auto-filter.
Admin-only routes additionally require `UserRole.admin`.

| Method | Path                              | Role       | Description                                          |
|--------|-----------------------------------|------------|------------------------------------------------------|
| GET    | `/api/v1/billing/plans`           | any user   | Public pricing catalog.                              |
| GET    | `/api/v1/billing/subscription`    | any user   | Current tenant's subscription (null when none).      |
| POST   | `/api/v1/billing/checkout`        | any user   | Returns a Stripe Checkout URL (or self-managed URL). |
| POST   | `/api/v1/billing/portal`          | admin      | Returns a Stripe Customer Portal URL.                |
| POST   | `/api/v1/billing/cancel`          | admin      | Schedule cancel-at-period-end.                       |
| POST   | `/api/v1/billing/resume`          | admin      | Undo a pending cancellation.                         |
| GET    | `/api/v1/billing/usage`           | any user   | Current period's metered usage.                      |
| GET    | `/api/v1/billing/invoices`        | any user   | List Stripe invoices for the tenant.                 |
| POST   | `/stripe/webhook`                 | public     | Stripe webhook handler. Signature-verified.          |

---

## 9. Troubleshooting

**Webhook returns 400.** Either the `Stripe-Signature` header is missing
or it doesn't verify against `STRIPE_WEBHOOK_SECRET`. Confirm the secret
matches the endpoint's signing secret in the Stripe Dashboard.

**Webhook returns 200 but nothing changes.** The handler probably
couldn't attribute the event to a tenant. Check that your prices have
`metadata.plan` set, and that the Checkout session was created with
`client_reference_id=<tenant_id>` (the backend always does this). Look
at the response body for `unattributed: true`.

**Tenant plan didn't update after Checkout.** The webhook for
`customer.subscription.created` may not have fired yet — Stripe is
eventually consistent. Refreshing the billing page within a few seconds
usually shows the new plan.

**Customer hit their AI cap unexpectedly.** Inspect
`GET /api/v1/billing/usage` — `ai_paid_usd_this_period` shows the
current spend, `ai_monthly_cap_usd` shows the included allowance.
Spend beyond the cap is metered and rolls onto the next invoice.
