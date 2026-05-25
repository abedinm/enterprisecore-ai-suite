# EnterpriseCore AI Suite — Build Status

Last refreshed 2026-05-21 after the four-phase multi-product consolidation.

## Consolidation landed 2026-05-21

Four new module groups merged in over five sessions, lifting the suite from a
single-SKU business platform to a three-SKU offering (Core / +EDU / +Verticals).
The architectural decisions live in [CONSOLIDATION_PLAN.md](CONSOLIDATION_PLAN.md);
license / pilot guidance lives in [SKU_FEATURES.md](SKU_FEATURES.md).

| Phase | Module | Source project absorbed | License tier |
|---|---|---|---|
| **1** | Web Chat Widget | F:\LinguaBot | Core |
| **2** | Marketing Site Builder (Studio + Renderer) | F:\CodexProjects\siteforge-studio | Core |
| **3** | Industry Templates (restaurant / consultancy / professional services) | F:\CornerTable, F:\MovedFromC\UserProjects\deltadesh, C:\Users\USER\Documents\deltadutch-website | Core |
| **4** | Academic Module Pack (11 sub-modules) | 11 student apps under F:\CodexProjects\ | +EDU |

What shipped alongside the modules:

- **License plan + SKU gating** — new `app/core/plans.py` with `Plan` enum
  (`evaluation` / `core` / `edu` / `verticals`) and `PLAN_FEATURES`. New
  `require_plan_feature(name)` dependency in `app/api/deps.py`. New
  `app/api/v1/endpoints/license.py` exposing `/status` and `/features`.
  Module catalog at `/api/v1/modules` now filters by active plan. Frontend
  reads `/license/features` on boot via `useLicenseFeatures()` and gates the
  nav with `useHasFeature(name)`.
- **Four new UserRoles**: `Student`, `Teacher`, `Registrar`, `Dean` — used
  only by the academic sub-routers, otherwise inert.
- **Three new migrations**: `0008_webchat`, `0009_marketing`, `0010_academic`
  (atop the pre-existing `0007_user_mfa_columns` from the previous session).
- **Public-facing routes**: `GET /widget.js` (embeddable widget script,
  plan-gated by `webchat` at the chat endpoint) and `GET /site/*` (Jinja2
  rendered marketing site, plan-gated by `marketing`).
- **Tests** grew from 289 → 413 (added: `test_plans.py`,
  `test_module_catalog_filtering.py`, `test_webchat_widget_serve.py`,
  `test_webchat_api.py`, `test_marketing_api.py`, `test_marketing_render.py`,
  `test_marketing_templates.py`, `test_academic_roles.py`,
  `test_academic_attendance.py`, `test_academic_timetable.py`,
  `test_academic_scaffolds.py`, `test_academic_plan_gating.py`).
- **Frontend** grew from 2475 → 2515 modules. New page bundles under
  `pages/webchat/`, `pages/marketing/` (16 pages), `pages/academic/` (15
  pages); new typed clients `lib/webchat.ts`, `lib/marketing.ts`,
  `lib/academic.ts`; new `hooks/useLicenseFeatures.ts`.
- **SKU structure** now: **Core** (every always-on module + webchat +
  marketing + templates) / **+EDU** (Core + academic) / **+Verticals**
  (Core + future vertical template packs).

What stayed out: HolyGrail (different liability surface, stays standalone).
Source customer sites (CornerTable / Deltadesh / Deltadutch) keep their
canonical locations — only the template *patterns* were extracted.

---

Previously refreshed 2026-05-20 after the AI Knowledge Hub overnight build and a sweep
through all module frontends.

## What's working today

### Foundation
- Project tree (`backend/`, `frontend/`, `electron/`, `installer/`, `docs/`)
- FastAPI app boots cleanly with **447 routes**
- SQLAlchemy 2.x ORM covering every module group
- JWT auth (HS256) with refresh-token rotation, login attempts table, audit log
- 4 roles (Admin / Manager / Developer / Employee) with `require_roles(...)` guard
- MFA columns on `users` (alembic 0007)
- Loguru structured logging to disk with rotation
- SQLite default + PostgreSQL switch via `DB_BACKEND`
- React 18 + Vite + TypeScript + Tailwind shell
- Persistent JWT auth with auto-refresh interceptor
- Dark / light / system theme
- i18n (en, es, fr, de)
- Online / offline indicator
- Global search, settings, dashboard, notifications, modules catalog

### Business Suite — all backends shipped, **all frontends now real**

Every module has a tabbed React UI mirroring the Finance pattern (no more
generic ModulePage placeholders).

| Module | Backend routes | Frontend tabs |
|---|---|---|
| Finance | 40+ | **15 tabs**: Dashboard, Invoices (PDF), Expenses, Payroll, Tax, Budgets, P&L (PDF), Balance Sheet (PDF), Cash Flow, Forecast, Currency, Multi-Currency, Recurring, Vendor Payments, Audit Trail |
| HR | 25+ | **12 tabs**: Employees, Attendance, Leave, Reviews, Recruitment, Onboarding, Org Chart, Payslips (PDF), Training, Self Service, Discipline, Analytics |
| CRM | 20+ | **12 tabs**: Customers, Leads, Pipeline (Kanban), Quotes, Proposals, Contracts, Campaigns, Comm Log, Follow-Ups, Forecast, Segments, Analytics |
| Projects | 20+ | **10 tabs**: Kanban, Gantt, Sprints, Milestones, Time Tracker, Resources, Workload, Scheduler, Meetings, Analytics |
| Inventory | 20+ | **10 tabs**: Catalog, Stock Manager, Warehouse, Purchase Orders, Suppliers, Shipments, Returns, Alerts, Barcode, Analytics |
| Documents | 15+ | **8 tabs**: Editor, PDF Export, E-Signature, Templates, Organizer, Versions, Bulk Rename, Sharing |
| Communication | 15+ | **8 tabs**: Messages, Announcements, Meetings, Calendar, Notes, Polls, Wiki, Feedback |
| Security | 15+ | **7 tabs**: Access, Audit Log, Login Monitor, GDPR, Compliance, Backups, Vault |

### AI Coding Assistant (15 tools — fully shipped)

All 15 tools functional, real working code, no placeholders. 60+ FastAPI routes,
10 React panels, 29 dedicated tests.

| Tool | Frontend | Backend |
|---|---|---|
| Monaco editor (tabs, dirty state, diff viewer) | ✅ | — |
| File tree / project explorer (CRUD, rename, hidden dirs) | ✅ | ✅ |
| Integrated terminal (xterm + allow-list sandbox) | ✅ | ✅ |
| AI chat (Claude/OpenAI/Ollama switch, context chips) | ✅ | ✅ |
| Code generation from English | ✅ | ✅ |
| Explanation + Docstring generator | ✅ | ✅ |
| Bug detector + auto-fixer w/ Monaco diff | ✅ | ✅ |
| Code review with JSON findings | ✅ | ✅ |
| Multi-file AI edit (plan → diff → apply) | ✅ | ✅ |
| Git integration (status/stage/commit/push/pull/branches/diff) | ✅ | ✅ |
| Syntax highlighting — 60+ languages | ✅ | ✅ |
| Snippet library + AI suggest | ✅ | ✅ |
| Postman-style API tester | ✅ | ✅ |
| DB query builder + visualizer (NL→SQL + schema browser) | ✅ | ✅ |
| Regex builder (live tester + AI explain + AI build) | ✅ | ✅ |

Plus **BYO API keys** with Electron `safeStorage` (OS-level encryption) and
**global shortcuts** (save, quick-open, panel cycle, close tab, jump-by-index).

### AI Brain
Unified `services/ai.py` abstraction over Anthropic, OpenAI, Ollama with
per-token cost tracking, automatic Ollama fallback, and a 30-day usage
dashboard. Endpoints: writer, meeting summariser, financial narration, HR
insights, sales forecast, invoice analysis, contract risk, smart search,
sentiment, regex-explain, chatbot builder.

### AI Knowledge Hub (landed 2026-05-20)
- Local-first RAG over user documents (4 new tables: `knowledge_bases`,
  `knowledge_documents`, `knowledge_chunks`, `knowledge_queries`)
- Streaming SSE chat for both general and RAG flows
- Citation rendering with `[N]` badges synced to a right-hand sources panel
- Ollama model manager UI (list / pull / status)
- Deterministic hash-pseudo embedding fallback so tests/dev work without Ollama
- 17/17 spec acceptance criteria green
- 4 frontend tabs added to AI Brain: Knowledge, RAG Chat, Model Manager,
  Documents Panel

### Packaging
- Electron main + preload that boots PyInstaller backend sidecar
- `electron-builder` config for NSIS .exe (with custom shortcuts)
- Inno Setup script alternative (`installer/inno-setup.iss`) with firewall option
- License-key env hook (`LICENSE_KEY`)
- Auto-updater wired via `electron-updater`
- **PyInstaller spec**: `backend/enterprisecore-backend.spec` — bundles uvicorn,
  FastAPI, SQLAlchemy, alembic + migrations, ReportLab + barcode formats.
  Produces a 77 MB `enterprisecore-backend.exe` that self-migrates on first run.
- **Stage script**: `scripts/stage-backend.js` copies the sidecar into
  `electron/resources/backend/` so electron-builder picks it up.
- **Frozen entry point**: `backend/runserver.py` — calls `uvicorn.run("app.main:app", …)`.
- **First .exe build: ✅ shipped this session.**
  - Output: `electron/dist/EnterpriseCore AI Suite Setup 0.1.0.exe` (241 MB NSIS)
  - Unpacked: `electron/dist/win-unpacked/` includes Chromium, the backend
    sidecar, frontend dist (asar-packed), and `elevate.exe`.
  - Boot path verified: pyinstaller exe runs uvicorn, alembic migrates to
    0007_user_mfa, scheduler starts, `/api/health` returns `{"status":"ok"}`.
  - **Known Windows-build issue**: electron-builder's winCodeSign extraction
    fails on Windows when Developer Mode is off (the cache archive contains
    macOS .dylib symlinks and 7za can't create them without
    SeCreateSymbolicLinkPrivilege). Workaround applied:
    pre-extract the cache excluding `darwin/` into
    `C:\Users\<u>\AppData\Local\electron-builder\Cache\winCodeSign\winCodeSign-2.6.0\`
    using `7za x -xr'!darwin*'`. This only needs to be done once per machine.

### Documentation
- `README.md` — quickstart
- `docs/USER_MANUAL.md` — full feature manual (now covers webchat, marketing, templates, academic)
- `docs/ARCHITECTURE.md` — stack, layout, data flow diagrams (now covers plan gating + public routes)
- `docs/AI_CODING.md` — coding-assistant docs
- `docs/AI_KNOWLEDGE_HUB.md` + `docs/AI_KNOWLEDGE_HUB_SPEC.md`
- `docs/CONSOLIDATION_PLAN.md` — architectural decisions from the Phase 0 sign-off
- `docs/SKU_FEATURES.md` — license issuance + plan / feature reference
- `docs/LICENSE.txt` — proprietary license template

## Health snapshot (this session)

- **Backend tests:** 206 passed, 0 failed, 0 skipped (`pytest -q`).
- **Frontend build:** `tsc -b && vite build` clean — 2475 modules, 17.5s.
- **Alembic chain:** 0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 (MFA fix
  this session — bad parent revision was breaking 3 migration tests).
- **Route count:** 447 across 18 route groups.

## What to build next

1. **Sign the .exe** — produce a code-signing cert (DigiCert/Sectigo) and wire
   it into electron-builder via `WIN_CSC_LINK` + `WIN_CSC_KEY_PASSWORD`. Until
   then SmartScreen will warn first-time users.
2. **First end-to-end smoke** through the packaged installer — run the
   installer on a clean VM, walk through login, open each module, create a
   record, kill and reopen.
3. **Inno Setup .exe** as a smaller alternative for users who don't want the
   Electron wrapper.
4. **CI** — wire `make test` into a GitHub Actions workflow and produce signed
   builds on tagged releases.
5. **Auto-updater** — host an electron-updater feed somewhere (S3, GitHub
   Releases, or self-hosted) and point the bundle at it.
