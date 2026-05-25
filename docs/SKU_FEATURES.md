# EnterpriseCore AI Suite — SKU & Features Reference

Operational reference for issuing licenses, picking the right SKU per
customer, and understanding what each plan unlocks. Read this before
generating a key for a paying customer or starting an EDU pilot.

For the architecture behind plan gating, see
[ARCHITECTURE.md](ARCHITECTURE.md#license-plan--sku-gating).
For the original design decisions, see
[CONSOLIDATION_PLAN.md](CONSOLIDATION_PLAN.md).

## The Plan enum

Defined in `backend/app/core/plans.py`. Every license payload carries a
`plan` field; that string is mapped onto this enum at request time by
`resolve_plan()`, which falls back to `EVALUATION` for missing, invalid,
or expired keys.

| Plan value     | Used when                                                    |
|----------------|--------------------------------------------------------------|
| `evaluation`   | No `LICENSE_KEY` set, or the key is invalid / expired        |
| `core`         | Default paid plan — every always-on module + webchat + marketing + templates |
| `edu`          | Core plus the academic module pack (schools, universities, training providers) |
| `verticals`    | Core plus future extra industry template packs (placeholder for now) |

Legacy keys with `plan="standard"` map automatically to `core` so older
issued licenses keep working without re-issuance.

## The PLAN_FEATURES map

Each plan unlocks a set of named features. Always-on platform modules
(auth, dashboard, settings, finance, hr, crm, projects, inventory,
documents, communication, security, coding, AI brain, knowledge hub) are
NOT in this map — they ship in every plan.

| Feature              | What it gates                                  | Evaluation | Core | EDU | Verticals |
|----------------------|------------------------------------------------|:---------:|:----:|:---:|:--------:|
| `webchat`            | `/api/v1/webchat/*`, `/widget.js`              | yes       | yes  | yes | yes      |
| `marketing`          | `/api/v1/marketing/*`, `/site/*` renderer      | yes       | yes  | yes | yes      |
| `marketing_templates`| Industry template gallery + apply action       | yes       | yes  | yes | yes      |
| `academic`           | `/api/v1/academic/*` (all 11 sub-modules)      | —         | —    | yes | —        |

The matrix above is the literal contents of `PLAN_FEATURES` — keep them
in sync when adding a new feature.

### How a request is gated

```
1. Frontend boots → useLicenseFeatures() queries /api/v1/license/features
2. /license/features → resolve_plan() → returns plan + sorted(features)
3. AppShell renders nav: useHasFeature("academic") hides the nav group
   when false; nav stays loading-blank until features arrive (no flash)
4. User hits an academic page → React route loads
5. Page calls /api/v1/academic/... → require_plan_feature("academic")
   raises PermissionDenied (HTTP 403) if the plan doesn't include it
6. Frontend treats 403 from a gated route as "show locked state" rather
   than redirect
```

Nothing in the stack lets a non-EDU install touch academic data — the
plan gate fires before role checks, before DB session use, before the
endpoint body runs.

## Issuing a license key

License keys are HMAC-signed JSON payloads of the form
`base64url(payload).base64url(signature)`. The signing secret is derived
from the install's `SECRET_KEY` for now; an offline issuance tool with a
dedicated long-lived secret is on the roadmap.

### From a Python REPL

```python
from app.core.license_key import make_demo_key

# 1-year EDU license for a university pilot
key = make_demo_key("Greenfield University", plan="edu", days=365)
print(key)
# eyJjdXN0b21lciI6Ikdyz...  (paste into the customer's .env as LICENSE_KEY=)

# 90-day Core trial for a prospect
key = make_demo_key("Acme Corp Trial", plan="core", days=90)

# Perpetual Core (set days to 36500 for ~100 years)
key = make_demo_key("Acme Corp", plan="core", days=36500)
```

The payload encodes `customer`, `plan`, `issued_on`, and `expires_on`.
`/api/v1/license/status` returns all four plus the verification state so
the customer's admin can confirm what they were given.

### Plan names accepted by `make_demo_key`

The `plan` argument is passed through verbatim into the payload. Use one
of: `evaluation`, `core`, `edu`, `verticals`, or the legacy `standard`
(maps to `core`). Anything else downgrades to `evaluation` at runtime.

### Setting the key in production

In the customer's `backend/.env`:

```env
LICENSE_KEY=<paste-the-key-here>
APP_ENV=production
```

Restart the backend. The license is verified once on startup
(`warn_on_license_startup()` in the FastAPI lifespan) — a green log line
confirms success, a yellow warning flags any issue. Live status is also
visible at `/api/v1/license/status` and rendered as a badge on the
Settings page of the suite.

### Rotating / replacing a key

Drop the new key into `.env` and restart. There is no online activation
step and no key revocation — keys are stateless and verified locally on
every request via the lightweight in-memory call to `verify_license()`.

## How the frontend nav respects the active plan

The nav is built from the module catalog that the frontend queries on
boot:

```
GET /api/v1/modules
→ returns { "groups": [ ...catalog rows whose feature is enabled... ] }
```

`MODULE_CATALOG` in `app/db/init_db.py` tags each group with an optional
`feature` field. The modules endpoint filters out any group whose feature
is not unlocked by the active plan before returning the list. Groups
without a `feature` field are always-on platform modules (finance, HR,
CRM, etc.) and are always returned.

The `AppShell` component then renders one nav section per returned
group. There is also a client-side belt-and-braces check via
`useHasFeature(name)` on the route components themselves, so a user who
manually types a URL into a feature they can't access lands on a locked
state rather than a partially-rendered page that would later 403 on its
data calls.

## Pilot guidance

### Piloting a customer on Core

Default starting point for any new customer. Workflow:

1. Spin up the customer's install with `LICENSE_KEY` empty — they're in
   evaluation, which has the same feature set as Core. Let them prove
   value over a 2-4 week trial.
2. Once they commit, issue a Core key with `make_demo_key("<customer>",
   plan="core", days=365)`. Drop it into their `.env`. The only behavioral
   change is the dashboard badge flips from "Evaluation" to "Active" and
   the startup log line confirms the signed customer name.
3. Renew yearly by issuing a fresh key — there is no online activation
   step, just paste the new key into `.env`.

### Piloting a school on EDU

The academic module is gated, so a Core pilot will not show academic to
the customer. To pilot the EDU SKU:

1. Issue a 60-day EDU key: `make_demo_key("<School Name> Pilot",
   plan="edu", days=60)`.
2. The school's admin pastes it into `.env` and restarts the backend.
3. The Academic nav group appears in the sidebar. The four academic
   roles (Student / Teacher / Registrar / Dean) become assignable from
   **Settings → Users**.
4. Walk the admin through the sample flow: create a semester + class +
   enrollments, assign a teacher, have them mark attendance, then have a
   student view their summary. Once that loop works, the rest of the
   module pack (timetable, LMS, exams, etc.) follows the same pattern.
5. After the pilot, convert to a multi-year EDU key (or downgrade to
   Core if academic isn't the right fit — the data stays in the DB but
   becomes inaccessible until EDU is re-enabled).

### When to pick Core vs EDU vs Verticals

- **Core**: every business — agencies, consultancies, restaurants,
  retailers, small B2B SaaS shops, contractors. Webchat + marketing
  alone replace several subscriptions for most of these.
- **EDU**: schools, universities, training providers, bootcamps,
  language schools — anywhere with students, teachers, classes,
  semesters, attendance, and grades.
- **Verticals**: placeholder for future extra template packs. Today it
  unlocks the same feature set as Core; the SKU exists so the upgrade
  path is in place before vertical packs ship. Don't issue Verticals
  yet unless we've agreed on what's in the pack for a specific customer.

### What evaluation mode actually gives away

Because `EVALUATION` has the same feature set as `CORE`, anyone running
without a key gets webchat, marketing, and the templates fully working.
The intended frictions are:

- Dashboard badge reads "Evaluation" instead of the customer name.
- Startup log line says "No LICENSE_KEY configured".
- License-status banner suggests installing a key for production.

This is deliberate — prospects can fully demo the suite locally before
paying. EDU stays gated because it's a distinct vertical SKU, not a demo
feature; a school can demo the academic UI by talking to us for a 14-day
EDU key.

## Tips and gotchas

- **Don't sign keys with a production secret from a dev machine.** The
  signing key is derived from `SECRET_KEY`. If dev and prod
  `SECRET_KEY` differ (they should), a key signed on dev will arrive at
  prod as `unverified` (not invalid — the suite still runs, but the
  status badge flags it). Sign customer keys on the same host or with a
  matching secret.
- **Backups carry over.** The `academic_*` / `webchat_*` / `marketing_*`
  tables live in the same SQLite / Postgres database as everything else,
  so the Security module's `BackupSchedule` already covers them. No
  per-module backup setup needed.
- **Switching plans mid-life works.** Drop in a new key, restart. Data
  in tables for now-disabled features stays put; it just becomes
  inaccessible until the feature is re-enabled. There is no destructive
  migration.
- **A user with an academic role but no EDU license is harmless.** The
  role assignment lands fine; the user just can't do anything with it
  until the license enables academic. Useful for pre-seeding accounts
  before a pilot starts.
- **The frontend caches `/license/features` for 5 minutes.** A key swap
  takes up to 5 minutes to show in the UI without a hard refresh; press
  Ctrl+R or hit the Refresh license action in Settings to clear it
  immediately.
- **Plan strings are case-insensitive on the way in.** `plan="EDU"`,
  `plan="Edu"`, and `plan="edu"` all resolve to `Plan.EDU`. Stick to
  lowercase when issuing for consistency.

## Quick reference

```python
# Inspect the live license
from app.core.license_key import verify_license
verify_license().to_dict()
# {
#   "valid": True,
#   "state": "active",
#   "reason": "Signature verified.",
#   "customer": "Greenfield University",
#   "plan": "edu",
#   "issued_on": "2026-05-21",
#   "expires_on": "2027-05-21",
#   "days_remaining": 365
# }

# Resolve current plan + features
from app.core.plans import resolve_plan, enabled_features
resolve_plan()       # <Plan.EDU: 'edu'>
enabled_features()   # {'academic', 'marketing', 'marketing_templates', 'webchat'}

# Gate an endpoint
from fastapi import Depends
from app.api.deps import require_plan_feature

@router.get("/secret", dependencies=[Depends(require_plan_feature("academic"))])
def secret_data(): ...
```
