# Data Migration Guide

EnterpriseCore ships with first-party importers so customers can move their
data in from the SaaS tools they're already running. The current importer
catalogue covers:

* **CRM / finance / HR**: HubSpot, Salesforce, QuickBooks, generic CSV.
* **Project management** (Phase 10): Asana, Notion, Trello, Microsoft
  Project. These land into the Projects module (`Project`, `Task`,
  `Resource`, `TaskDependency`) and optionally the Documents module
  (`Document` for Notion notes).

This guide walks through the workflow end-to-end, then breaks down the
quirks of each source. Every step is exposed as an HTTP endpoint under
`/api/v1/importers/*` and the web UI mirrors the same flow.

## The lifecycle

Every import — regardless of source — passes through the same six stages:

| Stage         | What it does                                                      |
|---------------|--------------------------------------------------------------------|
| `uploaded`    | The file is saved to `storage/imports/<job_id>.csv`.               |
| `validating`  | The importer dry-runs every row and reports issues.                |
| `previewing`  | A user-facing preview shows the first N rows fully mapped.         |
| `importing`   | Rows are written to the EnterpriseCore tables.                     |
| `completed`   | Job is finished; counts are final.                                 |
| `rolled_back` | Optional admin action — undoes the imported rows.                  |

All endpoints are tenant-scoped. Two customers in the same EC install
cannot see each other's import jobs, errors, or the data they brought in.

## Quick start (any source)

```bash
# 1. List available importers
GET /api/v1/importers

# 2. Upload your file (multipart)
POST /api/v1/importers/jobs
  source=hubspot
  target_entity=contact
  file=@hubspot-contacts.csv
# -> { "id": "<job_id>", "status": "uploaded", ... }

# 3. Inspect the schema we detected
POST /api/v1/importers/jobs/<job_id>/detect-schema

# 4. Get our auto-mapping
POST /api/v1/importers/jobs/<job_id>/suggest-mapping

# 5. Tweak the mapping if needed
PATCH /api/v1/importers/jobs/<job_id>/mapping
  { "column_mapping": { "Email": "email", "First Name": "first_name", ... } }

# 6. Dry-run validation
POST /api/v1/importers/jobs/<job_id>/validate

# 7. Eyeball the first 10 rows as they'd land
POST /api/v1/importers/jobs/<job_id>/preview?limit=10

# 8. Commit
POST /api/v1/importers/jobs/<job_id>/commit
# -> { "row_count_imported": 357, "row_count_skipped": 12, "row_count_failed": 0 }

# 9. (admin only) Roll back if something went wrong
POST /api/v1/importers/jobs/<job_id>/rollback
```

## Migrating from HubSpot

HubSpot publishes CSV exports from **Settings → Account Setup → Import &
Export**. EnterpriseCore handles three entities:

1. **Contacts** — `target_entity=contact`. Map `First Name` + `Last Name`
   to `name` (we concatenate), plus `Email`, `Phone Number`, `Company`.
2. **Companies** — `target_entity=customer`. The HubSpot "Company Name"
   becomes the Finance `Customer.name`.
3. **Deals** — `target_entity=deal`. `Deal name`, `Amount`, `Deal Stage`,
   and `Close Date` map directly.

The auto-mapper recognises HubSpot's column names out of the box; in most
cases you can accept the suggested mapping verbatim. Dedup defaults to
**by email** for contacts (`options.dedup_strategy = "by_email"`) — the
second import of the same export is a no-op.

### HubSpot pipeline stages

HubSpot's stage names (e.g. "Appointment Scheduled", "Decision Maker
Bought-In") don't match EnterpriseCore's CRM pipeline. The importer keeps
the source string in the EC `Deal.stage` field — your team can then
re-categorise via the pipeline view, or rename stages on the EC side to
match HubSpot's naming.

## Migrating from Salesforce

Use Data Loader (or any Salesforce report export) to produce CSV files
for the three entities:

1. **Contacts** — columns: `FirstName`, `LastName`, `Email`, `Phone`,
   `AccountName`. Maps the same way as HubSpot contacts.
2. **Accounts** → `target_entity=customer`. The `AccountName` column maps
   to `Customer.name`; `BillingStreet` / `BillingCity` to
   `billing_address`.
3. **Opportunities** → `target_entity=deal`. `Name`, `Amount`,
   `StageName`, `CloseDate`, `Probability` all map directly.

Dedup defaults to **by email** for contacts. Opportunities are not
deduplicated by default (no natural unique key) — set
`options.dedup_strategy = "by_name"` if you want one-shot re-runs to be
safe.

### REST API mode

When the customer would rather have EnterpriseCore pull data directly
from their Salesforce org — skipping the CSV-export step entirely — the
Salesforce importer also supports a REST mode. This requires a one-time
Connected App registration on the Salesforce side.

**One-time setup** (customer):

1. In Salesforce, go to **Setup → App Manager → New Connected App**.
   Enable OAuth with scopes ``api`` and ``refresh_token / offline_access``.
2. Note the Consumer Key + Consumer Secret. Provide these to your EC
   operator to set as ``SALESFORCE_CLIENT_ID`` and
   ``SALESFORCE_CLIENT_SECRET`` on the EC server.
3. Complete the OAuth flow once interactively (or via ``sf cli``) to
   obtain a ``refresh_token`` for the user you want EC to act as.

**Create a REST-mode job** (no file upload):

```bash
POST /api/v1/importers/jobs/api
{
  "source": "salesforce",
  "target_entity": "contact",
  "source_credentials": {
    "instance_url": "https://acme.my.salesforce.com",
    "refresh_token": "<refresh>",
    "sandbox": false
  }
}
```

The rest of the pipeline (detect-schema, suggest-mapping, validate,
preview, commit, rollback) works identically — the importer streams
records from the Salesforce REST query API
(``/services/data/v60.0/query/``) and pages through ``nextRecordsUrl``
until done OR the row cap (default 100,000) is hit.

If the credentials are stale, ``commit`` returns 401 with body
``"Refresh Salesforce credentials"`` so the SPA can prompt the user to
reauthorize the Connected App.

## Migrating from QuickBooks

QuickBooks (Online and Desktop) exports CSVs for:

1. **Customers** — columns: `CustomerName`, `PrimaryEmail`,
   `PrimaryPhone`, `BillingAddressLine1`. Dedup defaults to **by name**.
2. **Vendors** — columns: `VendorName`, `PrimaryEmail`, `PaymentTerms`.
   Dedup defaults to **by name**.
3. **Invoices** — columns: `DocNumber` (invoice number), `TxnDate`
   (issue date), `DueDate`, `TotalAmount`, `Customer`. Dedup defaults
   to **by invoice number** so a re-uploaded export is a no-op.
4. **Expenses** — columns: `TxnDate`, `Amount`, `Payee`, `Memo`.

### Invoice header vs. line-item format

QuickBooks invoice CSVs come in two shapes:

- **Header-only**: one row per invoice. Total is in `TotalAmount`.
- **Header + line items**: one row per line, with the invoice number
  repeated. Total is the sum of `LineAmount` values.

v1 of the EC importer handles the **header-only** format and writes a
single Invoice with the total. Most QuickBooks Online exports default to
this shape. Line-item splitting will land in the follow-up release once
customers ask for itemised import.

### QuickBooks Online API mode

For QuickBooks **Online** (not Desktop), EnterpriseCore can pull data
directly via Intuit's REST API. This requires a one-time app
registration in the Intuit Developer portal.

**One-time setup** (customer):

1. Sign in to ``developer.intuit.com``, create a new app under
   "My Apps", and enable the ``com.intuit.quickbooks.accounting`` scope.
2. Note the Client ID + Client Secret. The EC operator sets these as
   ``INTUIT_CLIENT_ID`` and ``INTUIT_CLIENT_SECRET`` in the EC
   environment.
3. Run the OAuth Playground once to obtain a ``refresh_token`` AND
   the ``realm_id`` (Intuit also calls it "company id") for the
   QuickBooks Online company you want EC to import from.

**Create a QBO-mode job**:

```bash
POST /api/v1/importers/jobs/api
{
  "source": "quickbooks",
  "target_entity": "customer",
  "source_credentials": {
    "realm_id": "1234567890",
    "refresh_token": "<refresh>",
    "sandbox": false
  }
}
```

The importer minted access token is short-lived (1 hour) — EC mints a
fresh one from the refresh token on every commit, so the customer
doesn't have to manage token rotation. The same lifecycle endpoints
(detect-schema, suggest-mapping, validate, preview, commit, rollback)
apply.

If the credentials are stale, ``commit`` returns 401 with body
``"Refresh QuickBooks credentials"``.

### Invoice customer linking

The "Customer" column on a QB invoice is a name, not a foreign key. The
importer stores it as a soft reference — to wire it to a Finance
`Customer` row, **import your QB customers list first**, then import
the invoices. The importer will look up the customer by name and fill
in `customer_id` automatically when it finds a match.

## Migrating from Asana

Asana → **Project menu → Export → CSV** produces one row per task with
these columns: `Task ID`, `Created At`, `Completed At`, `Last Modified`,
`Name`, `Section/Column`, `Assignee`, `Due Date`, `Tags`, `Notes`.

* `source=asana`, `target_entity=tasks` (also accepts `project`).
* The importer creates a single `Project` (named after the upload file,
  or pass `options.project_name` to override) and one `Task` per row.
* `Section/Column` is mapped to `Task.status` via a small lookup:
  `To do` → `todo`, `In progress` / `Doing` → `in_progress`,
  `Review` / `QA` → `in_review`, `Blocked` → `blocked`, `Done` → `done`.
  Anything unrecognised falls back to `todo`.
* The Task model has no `external_id` column. The importer stashes the
  Asana `Task ID` in `Task.tags` as `asana:<id>` so the same export can
  be re-imported safely — dedup matches on that marker and skips
  already-imported tasks.
* `Notes` lands in `Task.description`; `Due Date` in `Task.due_date`;
  `Tags` is concatenated into `Task.tags` after the marker.

## Migrating from Notion

Notion exports one CSV per database. `source=notion` is a Notion-aware
generic CSV importer — it doesn't assume a fixed column set because Notion
users freely rename columns and add emoji (`Due Date 📅`). Two target
entities:

* `target_entity=tasks` → one `Project` (override via
  `options.project_name`) plus one `Task` per row. The suggester
  recognises `Name` / `Task` / `Title` for the title, `Status` / `State` /
  `Stage` for status, `Due` / `Deadline` / `Date` for the due date,
  `Tags` / `Labels` / `Category` for tags, `Description` / `Notes` /
  `Body` for the body. Substring fallback handles emoji-suffixed columns.
* `target_entity=notes` → one `Document` per row, using the same synonym
  table but with a `content` column instead of `description`.

Dedup is by **name** within the project (tasks) or globally within the
tenant (notes), since Notion CSV exports don't ship a stable per-row id.

## Migrating from Trello

Trello → **Board menu → Show more → Print & Export → JSON**. The whole
board lands in one JSON document. `source=trello` accepts the file as-is.

* `target_entity=board` or `cards`. Both produce the same output: one
  `Project` (from the board `name`) and one `Task` per `card`.
* The card's list (`idList`) is resolved to the list `name` and mapped to
  `Task.status` via the same status-from-section table used by Asana.
* `labels` (joined by space) plus `trello:<card-id>` marker → `Task.tags`.
* `due` → `Task.due_date`. `desc` → `Task.description`, with any
  `checklists` appended as a `## Checklist name` heading followed by
  `- [x] item` / `- [ ] item` lines since the Task model has no native
  subtask field.
* Dedup is by Trello card `id` (via the `trello:` tag marker), within the
  project. Re-importing the same export is a no-op.

## Migrating from Microsoft Project

MS Project's binary `.mpp` format isn't supported (no permissive
parser). Instead, save the schedule as **Project XML** (`File → Save As
→ XML`). `source=microsoft_project`. Supported targets:

* `target_entity=project` — full import: Project, Tasks, Resources,
  and PredecessorLink dependencies in one shot.
* `target_entity=tasks` — tasks only.
* `target_entity=resources` — resources only.
* `target_entity=dependencies` — dependencies only (run after tasks).

Mapping:

* `Project/Name` → `Project.name` (override with `options.project_name`).
* Each `Task` → suite `Task`. The MSP `UID` is stored in `Task.tags` as
  `msp:<uid>` for cross-run dedup; the WBS path is also stored as
  `WBS=<n.n.n>` because the Task model has no native `parent_task_id`.
* `Start` / `Finish` → `Task.start_date` / `Task.due_date`.
* Each `Resource` → suite `Resource` (dedup by name).
* Each `PredecessorLink` → `TaskDependency` with
  `dep_type=finish_to_start`.

The parser tolerates both the namespaced
(`xmlns="http://schemas.microsoft.com/project"`) and namespace-less XML
that older Project versions emit. No third-party dependency — pure
stdlib `xml.etree.ElementTree`.

## Generic CSV

For everything else — Pipedrive, Zoho, an old spreadsheet, a SQL dump —
use `source=csv`. The flow is identical, but:

1. There is **no source-specific auto-mapping**. The generic mapper still
   recognises common synonyms (`Email` → `email`, `Phone` → `phone`),
   but you'll usually want to PATCH the mapping yourself.
2. You can target any of the entities the source-specific importers
   support: `contact`, `customer`, `vendor`, `deal`, `invoice`,
   `expense`, `employee`.
3. Set `options.dedup_strategy` to one of `by_email`, `by_name`,
   `by_invoice_number`, or `by_employee_code` — or leave it unset to
   import every row as a fresh record.

## Dedup strategies

The dedup strategy controls what happens when a row matches an existing
record:

| Strategy             | When to use                                              |
|----------------------|----------------------------------------------------------|
| `by_email`           | Contacts and customers with a primary email column.       |
| `by_name`            | Vendors, customers without a stable email.                |
| `by_invoice_number`  | Invoices — the natural unique key.                        |
| `by_employee_code`   | Employees — payroll-stable id from your HRIS.             |
| _unset_              | No dedup. Every row becomes a fresh record.               |

Pair with `options.on_conflict`:

- `skip` (default) — leave the existing row alone, increment the
  `row_count_skipped` counter.
- `update` — overwrite the existing row's fields with the new values.
- `create_duplicate` — insert a second record with the same dedup key.

## Rollback

Every job tracks the EC record ids it created in
`imported_record_ids`. `POST /importers/jobs/<id>/rollback` deletes
exactly those rows — nothing else. If the user has since edited the
imported records, those edits are lost; if they've created new
*related* rows (e.g. a follow-up on an imported contact), those related
rows are **not** touched.

Rollback is admin-only and one-shot. Once a job has status
`rolled_back`, it cannot be re-committed — upload the same file again
under a fresh job.

## Limits

- **File size**: 25 MB per upload. Larger? Split into multiple files.
- **Row count**: 200,000 hard cap per file; **100,000 recommended** for
  fast synchronous processing. Files near the cap may take several
  minutes to commit.
- **Concurrency**: imports are synchronous in v1. Don't kick off a
  second large job while the first is still importing in the same tenant.
- **Validation**: only checks required fields are present and mapped.
  Cross-row uniqueness (e.g. two rows with the same email in the same
  upload) is enforced at commit time by the dedup strategy.

## Troubleshooting

**"Required field 'name' is not mapped to any source column"**
Add the missing mapping via PATCH `/jobs/<id>/mapping`. The
`/suggest-mapping` endpoint will list every EC field the entity needs.

**"Row N: required field 'name' is empty"**
The source column is mapped, but row N has a blank value. Either fix
the upstream data or remove those rows from the CSV before uploading.

**Rows imported but show wrong values**
Run `/preview` *before* `/commit` to catch this. If you've already
committed, use `/rollback` (admin) and retry with a corrected mapping.

**"Job is not eligible for rollback"**
Some jobs (e.g. those imported via the future bulk-streaming endpoint)
opt out of rollback by setting `can_rollback=false`. For everything in
v1 rollback is on by default.
