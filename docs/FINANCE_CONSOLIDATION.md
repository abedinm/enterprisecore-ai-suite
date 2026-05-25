# Multi-Currency Consolidation & Multi-Entity Accounting

Phase 10 multinational feature for the EnterpriseCore Finance module.
Lets a single tenant model multiple legal entities (subsidiaries) in
different functional currencies and produce a consolidated balance sheet
+ P&L in any chosen reporting currency.

## Data model

Three new tables (see `app/models/finance_consolidation.py`):

| Table | Purpose |
|---|---|
| `subsidiary_entities` | A legal entity / subsidiary of the tenant (UK Ltd, SG Pte, etc.). One is flagged `is_main=True`. |
| `intercompany_transactions` | A loan / management fee / cost allocation / transfer between two entities of the same tenant. `eliminates_on_consolidation=True` rows wash out at consolidation. |
| `fx_adjustments` | Records FX gain/loss recognized when remeasuring foreign-currency monetary balances at period close. |

`invoices`, `expenses`, and `payroll_runs` gain a nullable `entity_id`
FK to `subsidiary_entities`. Migration `0023_finance_consolidation`
provisions a `MAIN` entity per tenant (using `tenants.currency` as both
functional and reporting currency) and backfills every existing row.

## Methodology (v1)

* **Balance sheet** — each entity's monetary balances are translated
  from its functional currency to the consolidation `target_currency`
  at the **closing rate** as of the report date. Fixed-asset historical
  rate translation is stubbed for v2 — v1 applies the closing rate to
  every asset.
* **P&L** — revenue + expenses are translated at the **period average
  rate**, computed from `currency_rates` snapshots that fall in the
  reporting window (falls back to the closing rate when no in-window
  snapshots exist).
* **Intercompany** — transactions flagged
  `eliminates_on_consolidation=True` are removed from both sides:
  the lender's receivable nets the borrower's payable, and matched
  IC revenue nets the matched IC expense.
* **CTA (cumulative translation adjustment)** — the residual gap
  between translated assets, liabilities, and equity is reported as
  a single `cta` line on the consolidated balance sheet output.
* **FX revaluation** — `fx_revaluation(entity, period_end)` walks
  the entity's AR (invoices in non-functional currencies) and AP
  (expenses in non-functional currencies), looks up the opening rate
  (30 days before `period_end`) and the closing rate, and persists an
  `FxAdjustment` row per (account_kind, currency) with the signed
  gain/loss.

## API surface (mounted under `/api/v1/finance`)

| Method | Path | Notes |
|---|---|---|
| GET | `/entities` | List subsidiaries for current tenant |
| POST | `/entities` | Admin-only. Rejects a second `is_main=True`. |
| PATCH | `/entities/{id}` | Admin-only. |
| DELETE | `/entities/{id}` | Admin-only. Blocks deletion when transactions reference the entity. |
| GET | `/intercompany` | List IC transactions, optional filter by from/to entity. |
| POST | `/intercompany` | Manager/admin. Same-tenant + distinct from/to enforced. |
| DELETE | `/intercompany/{id}` | Admin-only. |
| POST | `/consolidate/balance-sheet` | Query params: `as_of`, `target_currency`, `entity_ids[]`. |
| POST | `/consolidate/pnl` | Query params: `period_start`, `period_end`, `target_currency`, `entity_ids[]`. |
| POST | `/fx-revaluation` | Body `{entity_id, period_end}`. Admin-only. Persists FxAdjustment rows. |
| GET | `/fx-revaluation` | List previously recorded FX adjustments. |

All endpoints respect the tenant auto-filter — cross-tenant entities
are invisible by construction.

## What's stubbed in v1

* Fixed-asset historical-rate translation — currently applies the
  closing rate to every asset, like monetary items. v2 should track an
  `acquisition_rate` on individual asset records.
* Equity translation at historical rate is not modelled — the CTA
  line absorbs the residual.
* Minority-interest / non-controlling-interest accounting is not
  modelled.
* The opening rate for FX revaluation is fixed at 30 days before
  `period_end`. v2 should let the caller pin a specific opening date
  (e.g. prior month-end close).
* AP is computed from non-functional-currency expenses; a proper
  AP ledger (matching the existing AR ledger) is still a v2 item.
