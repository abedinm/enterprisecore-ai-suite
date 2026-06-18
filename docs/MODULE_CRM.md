# MODULE_CRM.md — Locked Spec (Phase 2)

> Definition-of-done benchmark for the CRM/Sales module. Frozen behaviour;
> update this doc in the same commit as any behaviour change. Verified
> against the live API + pytest on 2026-06-18.

## What it does

CRM is the second beachhead module. It runs the full sales motion:

| Sub-feature | Endpoint(s) | Status |
|---|---|---|
| Contacts | `GET/POST/PATCH/DELETE /crm/contacts` | Works, validated |
| Leads | `GET/POST/PATCH/DELETE /crm/leads` | Works, validated |
| Lead → deal convert | `POST /crm/leads/{id}/convert` | Works |
| Deals | `GET/POST/PATCH/DELETE /crm/deals` | Works, validated |
| Pipeline (kanban) | `GET /crm/deals/pipeline` | Works |
| Deal stage change | `POST /crm/deals/{id}/stage` | Works, enum-validated |
| **Deal → invoice** | `POST /crm/deals/{id}/invoice` | **Works (keystone integration)** |
| Follow-ups | `/crm/follow-ups` | Works |
| Communication log | `/crm/communications` | Works |
| Proposals | `/crm/proposals` (+ PDF) | Works |
| Quotations | `/crm/quotations` (+ PDF) | Works |
| Contracts | `/crm/contracts` | Works |
| Email campaigns | `/crm/campaigns` | Works |
| Segments | `/crm/segments` | Works (rule-based) |
| Sales analytics / forecast | `/crm/analytics`, `/crm/forecast` | Works |

## Pipeline rules (frozen)

- **Stages** (fixed set): `qualified → discovery → proposal → negotiation →
  won / lost`. Any other stage value is rejected with 422.
- **Probability** is 0–100 (percent). Out-of-range rejected.
- **Deal value** is `Decimal`, ≥ 0.
- Moving a deal to `won` fires the `crm.deal.won` event; `lost` fires
  `crm.deal.lost`. Subscribers (gamification, integrations) react to these.

## The keystone: Deal → Invoice (frozen)

`POST /crm/deals/{id}/invoice` is the integration that makes this a *suite*
rather than two silos. Behaviour:

1. Requires **Admin or Manager** (invoicing is a finance-write action).
2. Finds-or-creates a Finance **Customer** from the deal's contact —
   matched by contact email, then company name, else a new customer is
   created. Repeated conversions for the same client reuse one customer.
3. Creates a **draft invoice** for the deal value, due in 30 days, with one
   line described by the deal title.
4. **Idempotent.** The invoice is tagged `[from-deal:<deal_id>]` in its
   notes. A second call returns the existing invoice (`created: false`)
   instead of duplicating.
5. Rejects deals with **zero/negative value** → 422 `deal_not_invoiceable`
   with a friendly message ("add a deal value first").
6. On success, emits `finance.invoice.created` with `source: crm_deal`.

Frontend: a **"Create invoice"** button appears on any won deal card in the
Pipeline tab; success pops confetti + a toast and refreshes the invoice
list.

## Input validation (Phase 2 hardening — frozen)

| Rule | Rejected example |
|---|---|
| Contact name non-blank | `"   "` |
| Contact email well-formed | `"nope"` |
| Contact phone valid chars | `"abc!!!"` |
| Deal title non-blank, ≤180 | `""` |
| Deal value ≥ 0 | `-500` |
| Deal probability 0–100 | `150` |
| Deal stage ∈ stage set | `"banana"` |
| Lead status ∈ {new, contacted, qualified, unqualified, converted} | `"xyz"` |
| Lead score 0–100 | `999` |

All return **422 with a friendly `detail`**, never a crash.

## Data integrity (verified)

- Create / edit / delete persist (create→reload confirmed).
- Deleting a contact sets dependent deals'/leads' `contact_id` to NULL
  (`ondelete=SET NULL`) — the deal survives, just unlinked.
- The deal→invoice bridge is duplicate-safe (idempotency test).

## Permissions (frozen)

- Reads: any authenticated tenant user.
- Writes + invoice generation: Admin/Manager server-enforced.
- Tenant-scoped throughout.

## Known limits / honest issues

1. **Pipeline is dropdown-driven, not drag-and-drop.** Stage changes via a
   `<select>`, not a draggable kanban. (Keyboard-accessible by design.)
2. **No automatic deal→invoice on "won".** Conversion is an explicit button,
   not a silent auto-post — deliberate, to avoid duplicate/premature
   invoices. An opt-in event subscriber hook exists but ships off.
3. **Email campaigns track counts but don't actually send** — there's no
   SMTP/ESP integration wired in the demo path.
4. **Segments are rule-based JSON**, evaluated on read; no materialised
   segment membership table.
5. **Forecasting is a simple weighted-pipeline sum**, not an ML model.

## How to verify (one command)

```bash
cd backend && ENTERPRISECORE_DISABLE_CSRF=1 python -m pytest \
  tests/test_phase2_finance_crm.py tests/test_crm_service.py -q
```
