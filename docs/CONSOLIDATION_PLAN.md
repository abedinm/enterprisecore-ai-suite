# EnterpriseCore — Multi-Product Consolidation Plan

**Status:** PHASE 0 — Architecture decisions pending user sign-off.
No code has been written. Once approved, Phase 1 (Web Chat Widget) starts.

---

## What we're absorbing

Four standalone projects fold into EnterpriseCore as first-class modules,
and 11 student apps reframe as an EDU SKU.

| Source project | Becomes | SKU |
|---|---|---|
| `F:\LinguaBot\` | `app/api/webchat/` + public `/widget.js` | Core |
| `F:\CodexProjects\siteforge-studio\` | `app/api/marketing/` + `/site/*` renderer | Core |
| `F:\CornerTable\`, `F:\MovedFromC\UserProjects\deltadesh\`, `C:\Users\USER\Documents\deltadutch-website\` | 3 template descriptors under `app/data/marketing_templates/` | Core |
| 11 student apps (`F:\CodexProjects\*`) | `app/api/academic/*` | EDU |

`F:\HolyGrail\` does NOT fold in — different liability surface, stays standalone.

---

## Reconnaissance findings

What already exists that we can leverage:

- **`app/core/license_key.py`** — license signing + verification is already
  built. `LicenseStatus` already has a `plan` field. Payload format:
  `{"customer": ..., "plan": "standard", "issued_on": ..., "expires_on": ...}`.
  But there is **NO enforcement** — `plan` is just metadata today.
- **`app/api/v1/endpoints/modules.py`** — already exposes a module catalog
  to the frontend (currently returns everything from `MODULE_CATALOG` in
  `db/init_db.py`). This is the natural gating point.
- **`app/models/crm.py`** already has `Contact` and `CommunicationEntry`.
  Web chat conversations get a `contact_id` FK and write timeline entries
  to `CommunicationEntry` — no new "visitor" table needed.
- **`app/services/ai.py`** is the multi-provider gateway. LinguaBot's
  standalone AI client gets dropped; webchat uses this gateway.
- **`app/core/rate_limit.py`** — sliding-window limiter exists. LinguaBot's
  standalone limiter gets dropped.
- **`app/api/v1/endpoints/auth.py:302-362`** — avatar upload pipeline
  (MIME allow-list, 2MB cap, EXIF strip via PNG re-encode). Reuse for
  marketing module image uploads.

What's missing (we will add):

- A `PLAN_FEATURES` map + `require_plan_feature()` FastAPI dependency
- Plan enforcement in `modules.py` (filter catalog by license plan)
- Frontend nav gating based on `/api/v1/license/status` plan

---

## Architecture decisions

### Q1 — Does the suite already have a feature-flagging / module system?

**A — Partially.** License verification exists; module catalog endpoint
exists; SKU enforcement does NOT exist yet. We add a thin layer on top
rather than build a plugin system.

### Q2 — How are new modules gated?

**A — Option (b): shipped in core, gated by license plan.**

Implementation:

```python
# app/core/plans.py  (new file, ~30 lines)
from enum import Enum

class Plan(str, Enum):
    EVALUATION = "evaluation"
    CORE = "core"        # default paid plan, what "standard" upgrades to
    EDU = "edu"          # adds academic module pack
    VERTICALS = "verticals"  # adds industry template gallery extras

PLAN_FEATURES: dict[Plan, set[str]] = {
    Plan.EVALUATION: {"webchat", "marketing", "marketing_templates"},
    Plan.CORE:       {"webchat", "marketing", "marketing_templates"},
    Plan.EDU:        {"webchat", "marketing", "marketing_templates", "academic"},
    Plan.VERTICALS:  {"webchat", "marketing", "marketing_templates"},
}

def has_feature(feature: str) -> bool:
    from app.core.license_key import verify_license
    status = verify_license()
    plan_name = (status.plan or "evaluation").lower()
    try:
        plan = Plan(plan_name)
    except ValueError:
        plan = Plan.EVALUATION
    return feature in PLAN_FEATURES.get(plan, set())
```

```python
# app/api/deps.py  (extend existing file)
from app.core.exceptions import PermissionDenied
from app.core.plans import has_feature

def require_plan_feature(feature: str) -> Callable:
    def _dep() -> None:
        if not has_feature(feature):
            raise PermissionDenied(
                f"Feature '{feature}' requires a higher license tier."
            )
    return _dep
```

Usage on academic endpoints:
```python
@router.get("/attendance", dependencies=[Depends(require_plan_feature("academic"))])
def list_attendance(...): ...
```

`modules.py` filters `MODULE_CATALOG` based on `has_feature(...)` so the
frontend only sees enabled modules.

### Q3 — CRM ↔ Web Chat data model

**A — Reuse existing CRM tables; add three new ones for chat.**

New tables in `app/models/webchat.py`:
- `Bot` — owner_id (FK User), name, system_prompt, model, languages,
  is_public, api_key_encrypted (Fernet)
- `Conversation` — bot_id FK, contact_id FK (nullable — only set once
  visitor identifies), visitor_session_id, started_at, last_message_at
- `ChatMessage` — conversation_id FK, role (user/assistant), content,
  tokens_in, tokens_out, language_detected, created_at

Linkage logic (in `app/services/webchat.py`):
1. New conversation starts → only `visitor_session_id` populated
2. Visitor message contains email/phone → call CRM's existing contact
   matcher (or create new `Contact` if no match) → set
   `Conversation.contact_id`
3. On every message, write a row to `CommunicationEntry` (existing CRM
   timeline table) with `kind="webchat"`, `contact_id`, content excerpt,
   FK back to the chat message. This is what makes the conversation
   appear in the CRM contact's timeline.

Why this design: zero new "visitor" table, zero CRM schema changes,
contacts ledger stays the single source of truth, chat history is fully
queryable from the contact's timeline.

### Q4 — Marketing data: same SQLite or sidecar?

**A — Same SQLite, prefixed table names.**

New tables: `marketing_pages`, `marketing_sections`, `marketing_portfolio_items`,
`marketing_blog_posts`, `marketing_business_profile`, `marketing_branding`.

Reasons:
- Single backup zip covers everything (Security module's BackupSchedule
  already snapshots the main DB)
- Image uploads share the existing `storage/uploads/` tree
- Cross-module joins become possible (e.g. "blog post mentions a Deal" —
  later feature)
- WAL mode is already on per `ARCHITECTURE.md`, so write contention is
  negligible for a single-user desktop app

### Q5 — HolyGrail integration?

**A — Stays standalone.** Crisis-detection / therapy modes carry employer-
liability risk if folded into HR. Different go-to-market (consumer vs B2B).
No code changes; no mention in EnterpriseCore.

---

## Phase-by-phase summary

| Phase | Scope | Sessions | Key migrations | Test target |
|---|---|---|---|---|
| **0** (this) | Architecture decisions, this doc | 1 | none | n/a |
| **1** | Web Chat Widget module + CRM linking + public widget.js | 1-2 | `0007_webchat.py` | all 289 still pass + new webchat tests |
| **2** | Marketing Site Builder (Studio + Preview renderer) | 2-3 | `0008_marketing.py` | all previous still pass + marketing tests |
| **3** | 3 industry template descriptors + "Use Template" action | 1 | none (data files) | template instantiation tests |
| **4** | Academic Module Pack (gated by EDU license) | 3-4 | `0009`..`0019` per academic module | attendance + timetable fully tested, others scaffolded |

---

## Cross-cutting work that happens in Phase 1 (not in any phase doc above)

These are needed before any new module can be gated, so they ship as part
of Phase 1 even though they aren't strictly webchat:

1. **Create `app/core/plans.py`** with `Plan` enum + `PLAN_FEATURES` map +
   `has_feature()` helper.
2. **Extend `app/api/deps.py`** with `require_plan_feature()`.
3. **Update `app/api/v1/endpoints/modules.py`** to filter the catalog by
   plan features (evaluation/core gets webchat + marketing; edu also gets
   academic).
4. **Update `app/api/v1/endpoints/license.py`** (if it exists, otherwise
   create) to surface the resolved plan + feature list to the frontend.
5. **Update `MODULE_CATALOG`** in `db/init_db.py` so each entry has a
   `feature: str` field that maps to `PLAN_FEATURES`.
6. **Frontend nav** — `AppShell.tsx` reads license status on boot and
   hides nav items whose `feature` is disabled.

Tests for the cross-cutting work:
- `tests/test_plans.py` — `has_feature` returns correct values for each
  plan, edu plan unlocks academic, evaluation plan unlocks core features
  only, expired license downgrades to evaluation.
- `tests/test_module_catalog_filtering.py` — `/api/v1/modules` returns
  filtered catalog based on license plan.

---

## Migration / decommissioning

Once each source project lands in EnterpriseCore:

- **LinguaBot** — write `scripts/migrate_from_linguabot.py` after Phase 1
  ships. Reads from `F:\LinguaBot\backend\storage\linguabot.db` (or
  whatever the SQLite path is) and imports bots + conversations into the
  new schema. Don't delete `F:\LinguaBot\` until the user confirms data
  integrity post-migration.
- **SiteForge Studio** — no migration needed; SiteForge was
  localStorage-only. The first time a user opens the Marketing module in
  EnterpriseCore, they get empty state. Optional: import-from-JSON tool
  if a user has a SiteForge export.
- **CornerTable / Deltadesh / Deltadutch** — these are real customer
  sites, NOT to be migrated; they keep their canonical locations. We
  only extract template *patterns* (layout, sections, styling) into the
  3 template descriptors in Phase 3.
- **Student apps** — extract patterns into academic modules in Phase 4.
  The original student apps stay as-is for individual student use; only
  the institutional analogues live in EnterpriseCore.

---

## What I need from you before Phase 1

Three sign-offs:

1. **Plan/SKU naming.** Is `Core / +EDU / +Verticals` the right SKU
   structure? Or do you prefer `Standard / Professional / Education`?
   Pricing-tier names affect the license `plan` enum.
2. **Evaluation vs. paid gating.** Do you want webchat + marketing
   available in evaluation mode (current proposal) or locked behind a
   paid `Core` license? I leaned permissive so demos work, but the call
   is yours.
3. **HolyGrail boundary.** Confirm HolyGrail stays standalone. The plan
   assumes yes; if you'd rather fold its therapist/scheduler tooling
   into HR Wellness, the liability conversation needs to happen first.

Once you sign off, Phase 1 starts: cross-cutting plan/SKU plumbing +
Web Chat Widget module. Estimated 1-2 sessions.
