# MODULE_FINANCE.md — Locked Spec (Phase 2)

> This is the **definition-of-done benchmark** for the Finance module.
> Behaviour described here is frozen. Don't change it without updating this
> doc in the same commit. Verified against the live API + pytest on
> 2026-06-18.

## What it does

Finance is the strongest, most production-shaped module in the suite. It
handles the full small-business money workflow:

| Sub-feature | Endpoint(s) | Status |
|---|---|---|
| Customers | `GET/POST/PATCH/DELETE /finance/customers` | Works, validated |
| Vendors | `GET/POST/PATCH/DELETE /finance/vendors` | Works, validated |
| Invoices (+ lines) | `GET/POST/PATCH/DELETE /finance/invoices` | Works, validated |
| Invoice status | `POST /finance/invoices/{id}/status` | Works, enum-validated |
| Invoice PDF | `GET /finance/invoices/{id}/pdf` | Works (reportlab) |
| Expenses | `GET/POST/PATCH/DELETE /finance/expenses` | Works |
| Expense categories | `GET/POST/DELETE /finance/expense-categories` | Works |
| Payroll runs | `GET/POST/DELETE /finance/payroll` | Works (pulls HR employees) |
| Budgets | `GET/POST /finance/budgets` | Works |
| Tax rates | `GET/POST /finance/tax-rates` | Works |
| Currency rates + convert | `/finance/currency/*` | Works (ISO-4217) |
| Recurring payments | `/finance/recurring` | Works |
| Vendor payments | `/finance/vendor-payments` | Works |

## Money + data rules (frozen)

- **All money is `Decimal`, 2 dp.** Never a binary float. Stored as
  `Numeric(14,2)`.
- **Currencies are ISO-4217**, validated against `SUPPORTED_CURRENCIES`
  (20 codes incl. USD/EUR/GBP/BDT). An unknown code is rejected with 422.
- **Invoice totals are server-computed** by `recompute_invoice()` —
  subtotal + tax − discount. The client never sets the total directly.
- **Timestamps are UTC.**

## Input validation (Phase 2 hardening — frozen)

Every write is validated at the Pydantic schema layer. Bad input returns
**422 with a friendly `detail` message**, never a crash or a corrupt save:

| Rule | Rejected example |
|---|---|
| Customer/vendor name non-blank | `"   "` |
| Email well-formed | `"not-an-email"` |
| Phone digits/spaces/`+-()` only, 6–32 chars | `"abc!!!"` |
| Currency is supported ISO-4217 | `"XYZ"` |
| Invoice line description non-blank | `""` |
| Line quantity > 0 | `0`, `-1` |
| Line unit price ≥ 0 | `-50` |
| Tax rate in 0..1 | `1.5` |
| Discount ≥ 0 | `-10` |
| Due date ≥ issue date | `due < issue` |
| Invoice status ∈ {draft, sent, paid, overdue, void} | `"banana"` |
| Money ≤ 99,999,999,999.99 | absurd values |

## Integrations (frozen)

- **HR → Payroll**: payroll runs iterate the `employees` table; payslip
  lines carry the real `employee_id`. Same dataset, FK-linked.
- **CRM → Finance**: a won deal can generate a draft invoice via
  `POST /crm/deals/{id}/invoice` (see MODULE_CRM.md). The invoice is tagged
  `[from-deal:<id>]` in its notes for idempotency.
- **Search**: invoices/customers/expenses are indexed in FTS5 and appear in
  global search.

## Data integrity (verified)

- Create / edit / delete all persist (confirmed by create→reload tests).
- **Deleting an invoice cascade-deletes its lines** (`ondelete=CASCADE`,
  verified by `test_invoice_delete_cascades_lines`).
- Deleting a customer sets dependent invoices' `customer_id` to NULL
  (`ondelete=SET NULL`) — invoices survive, just unlinked.
- No duplicate invoice numbers — `next_invoice_number()` is monotonic.

## Permissions (frozen)

- Reads: any authenticated user in the tenant.
- Writes (create/update/delete, status changes, invoice generation):
  **Admin or Manager only** (`require_roles`). Enforced server-side; a
  low-role user calling the API directly gets 403.
- All data is tenant-scoped — a user only ever sees their own org's finance.

## Known limits / honest issues

1. **No double-entry ledger.** Invoices/expenses are records, not a true
   general ledger with debits/credits. Fine for SMB invoicing; not
   audit-grade accounting.
2. **No partial-payment schedule.** An invoice is draft → sent → paid; you
   can record a payment but not an instalment plan.
3. **Currency conversion uses the latest stored rate**, not a historical
   rate per transaction date.
4. **PDF generation is synchronous** — a very large invoice blocks the
   request briefly. Acceptable at SMB scale.
5. **Tax is a flat per-line rate**, not a jurisdiction-resolved tax engine.

## How to verify (one command)

```bash
cd backend && ENTERPRISECORE_DISABLE_CSRF=1 python -m pytest \
  tests/test_phase2_finance_crm.py tests/test_finance.py \
  tests/test_finance_service.py tests/test_services_finance.py -q
```
