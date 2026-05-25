# EnterpriseCore AI Suite — Architecture

## Stack

| Layer | Technology | Notes |
|---|---|---|
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS | SPA, persistent JWT auth, dark/light theme via CSS vars |
| State | Zustand + TanStack Query | Persistent auth + theme stores; query cache invalidation on mutations |
| Editor | Monaco | Full IDE experience inside the AI Coding module |
| Charts | Recharts | KPIs, bar/line/pie/composed |
| Backend | FastAPI (Python 3.11+) + SQLAlchemy 2.x | Async-friendly endpoints, pydantic v2 schemas |
| Database | SQLite (default) / PostgreSQL (optional) | Switch via `DB_BACKEND` env. Schema is auto-created on first boot |
| AI | Anthropic + OpenAI + Ollama | Unified `services/ai.py` with auto-fallback to Ollama |
| Desktop | Electron + electron-builder | Bundles backend as PyInstaller sidecar |
| Installer | NSIS (electron-builder) and Inno Setup | Both supported |

## Process model

```
┌─────────────────────────────────────────────────────────────┐
│  Electron main process                                      │
│    ├── spawns FastAPI sidecar (PyInstaller exe in prod)     │
│    ├── waits for /api/health                                │
│    └── loads React build into BrowserWindow                 │
└─────────────────────────────────────────────────────────────┘
              │                                  │
              ▼                                  ▼
   ┌─────────────────────┐         ┌──────────────────────────┐
   │  FastAPI @ :8765    │◄────────│  React @ :5173 (dev)     │
   │   - JWT auth        │  HTTP   │  or file:// (prod)       │
   │   - 21 module APIs  │ +-token │  - Monaco IDE            │
   │   - SQLAlchemy ORM  │         │  - 130+ tools UIs        │
   │   - Ollama/Claude   │         │  - i18n (4 languages)    │
   │   - /widget.js      │         │  - License-aware nav     │
   │   - /site/* (Jinja2)│         │                          │
   └─────────────────────┘         └──────────────────────────┘
              │
              ▼
   ┌─────────────────────────────────────────────────────────┐
   │  storage/                                               │
   │   ├── enterprisecore.db    (SQLite, WAL mode)           │
   │   ├── uploads/             (user files, encrypted)      │
   │   ├── backups/             (zipped snapshots)           │
   │   ├── reports/             (generated PDFs)             │
   │   └── logs/                (rotating loguru output)     │
   └─────────────────────────────────────────────────────────┘
```

## Backend layout

```
backend/app/
├── main.py                 FastAPI app, lifespan, CORS, static files, /widget.js, /site/*
├── core/
│   ├── config.py           pydantic-settings, env-driven
│   ├── security.py         bcrypt, JWT (HS256), Fernet encryption
│   ├── exceptions.py       Typed app errors + global handlers
│   ├── logging.py          Loguru with file rotation
│   ├── license_key.py      HMAC-signed license parse/verify + make_demo_key()
│   └── plans.py            Plan enum + PLAN_FEATURES + resolve_plan / has_feature
├── db/
│   ├── session.py          SQLAlchemy engine, SQLite PRAGMAs
│   ├── base.py             Declarative base, IdMixin, TimestampMixin
│   └── init_db.py          create_all + seed admin + module catalog (with feature tags)
├── models/                 One file per module group
│   ├── user.py             User, RefreshToken, Setting, AuditLog, Notification, SearchIndex
│   ├── finance.py          Customer, Vendor, Invoice/Line, Expense, Payroll, Budget, Tax…
│   ├── hr.py               Employee, Attendance, Leave, Review, Candidate, OrgUnit…
│   ├── crm.py              Contact, Lead, Deal, FollowUp, Contract, Quotation, Campaign…
│   ├── projects.py         Project, Task, Sprint, Milestone, TimeEntry, Meeting
│   ├── inventory.py        Product, StockMovement, PO, Shipment, Return, Supplier…
│   ├── documents.py        Document + Version + Tag + Share + ESignature + Template
│   ├── communication.py    Messages, Announcements, Calendar, Notes, Polls, Wiki…
│   ├── security.py         PasswordVault, BackupSchedule, LoginAttempt, ComplianceCheck
│   ├── coding.py           CodeProject, CodeSnippet, ApiRequest, GitRepo
│   ├── ai.py               AiConversation, AiMessage, AiUsageRecord, Chatbot…
│   ├── knowledge.py        KnowledgeBase, KnowledgeDocument, KnowledgeChunk, KnowledgeQuery
│   ├── webchat.py          Bot, Conversation, ChatMessage (CRM-linked)
│   ├── marketing.py        MarketingSettings, NavItem, Section, Project, Post, Service,
│   │                         Testimonial, FAQ, TeamMember, SocialLink, Upload
│   └── academic/           Sub-package — one file per academic domain
│       ├── core.py             AcademicSemester, AcademicRoom
│       ├── classes.py          AcademicClass, AcademicClassEnrollment
│       ├── attendance.py       AcademicAttendanceRecord
│       ├── timetable.py        AcademicTimetableSlot
│       ├── lms.py              AcademicLmsResource
│       ├── lab_reports.py      AcademicLabReport
│       ├── exams.py            AcademicExam
│       ├── advising.py         AcademicAdvisingSession
│       ├── group_projects.py   AcademicGroupProject, AcademicGroupProjectAssignment
│       ├── study_aids.py       AcademicStudyNote
│       ├── study_match.py      AcademicStudyProfile, AcademicStudyGroupMatch
│       ├── finance.py          AcademicScholarship, AcademicStudentFinanceRecord
│       └── deadlines.py        AcademicAssignment, AcademicAssignmentSubmission
├── schemas/                One file per module — pydantic request/response models
│                             (academic/ is also a sub-package mirroring models/academic)
├── services/               Business logic that's heavier than a CRUD route
│   ├── audit.py                Centralized audit logging
│   ├── finance.py              Invoice math, P&L, balance sheet, cash flow, forecast, PDF
│   ├── ai.py                   Multi-provider AI calls with cost tracking
│   ├── knowledge.py            RAG ingest + retrieval + citations
│   ├── webchat.py              Language detect, CRM contact resolve, AI dispatch, timeline write
│   ├── marketing.py            Settings singleton, slugify, EXIF-stripped uploads, template apply
│   ├── academic_attendance.py  Bulk-mark, per-session view, per-student summary
│   └── academic_timetable.py   Slot scheduling w/ conflict checks, role-specific views
├── templates/marketing/    Jinja2 templates for the rendered public site
│   ├── base.html
│   ├── home.html, about.html, services.html, contact.html
│   ├── portfolio.html, project.html
│   └── blog.html, post.html
├── data/marketing_templates/   Shipped industry template JSON descriptors
│   ├── restaurant.json
│   ├── consultancy.json
│   └── professional_services.json
├── static/
│   └── widget.js           Embeddable chat widget served at /widget.js (CORS *)
└── api/
    ├── deps.py             get_db, get_current_user, require_roles, require_plan_feature
    └── v1/
        ├── router.py       Aggregates all module routers
        └── endpoints/      One file per module
            ├── auth.py           login/register/refresh/me/password
            ├── users.py          admin user management
            ├── dashboard.py      KPI rollup across modules
            ├── settings.py       global config kv store
            ├── notifications.py  in-app alerts
            ├── search.py         cross-module text search
            ├── modules.py        feature catalog (filters by plan)
            ├── license.py        /license/status + /license/features
            ├── finance.py        15+ tools, 40+ routes
            ├── hr.py
            ├── crm.py
            ├── projects.py
            ├── inventory.py
            ├── documents.py
            ├── communication.py
            ├── security_mod.py
            ├── coding.py         + AI codegen/review/bugfix
            ├── ai.py             + chatbot builder, smart search
            ├── knowledge.py      RAG admin + streaming chat
            ├── webchat.py        Bot CRUD + conversation viewer + /chat/{bot_id} public
            ├── marketing.py      Studio admin + templates apply
            ├── marketing_site.py /site/* public renderer (mounted by main.py)
            └── academic/         Sub-package — one file per academic sub-module
                ├── router.py     Parent router with require_plan_feature("academic")
                ├── _common.py    Shared role bundles (TEACHER_OR_ADMIN, REGISTRAR_OR_ADMIN, ...)
                ├── core.py       Semesters + rooms
                ├── classes.py
                ├── attendance.py
                ├── timetable.py
                ├── lms.py
                ├── lab_reports.py
                ├── exams.py
                ├── advising.py
                ├── group_projects.py
                ├── study_aids.py
                ├── study_match.py
                ├── finance.py
                └── deadlines.py
```

## Frontend layout

```
frontend/src/
├── main.tsx, App.tsx       Router, QueryClient, theme bootstrap
├── components/layout/
│   └── AppShell.tsx        Sidebar nav, header, online/offline badge (license-aware)
├── pages/
│   ├── auth/               Login, Register
│   ├── dashboard/          KPI home
│   ├── search/             Global search UI
│   ├── settings/           Configuration grid
│   ├── finance/            15 tabs (Invoices, P&L, Cash Flow, etc.)
│   ├── coding/             Monaco IDE + AI chat + Terminal + Git panel
│   ├── webchat/            BotList, BotEditor, ConversationsViewer, EmbedSnippetGenerator,
│   │                         TestSandbox
│   ├── marketing/          MarketingLayout + Dashboard, Settings, Navigation, Pages,
│   │                         Portfolio (+ PortfolioEditor), Blog (+ BlogEditor), Services,
│   │                         Testimonials, FAQs, Team, Social, Media, Templates
│   ├── academic/           AcademicLayout + Dashboard, Classes, ClassDetail, Attendance,
│   │                         Timetable, LmsLibrary, LabReports, Exams, Advising,
│   │                         GroupProjects, StudyAids, StudyBuddies, Finance, Deadlines
│   └── ModulePage.tsx      Generic placeholder for modules not yet UI-implemented
├── store/
│   ├── auth.ts             Zustand store w/ token refresh
│   └── theme.ts            Light/dark/system
├── lib/
│   ├── api.ts              Axios client + interceptors + token store
│   ├── utils.ts            Currency/date formatters, cn()
│   ├── knowledge.ts        RAG client (typed wrappers over /knowledge/*)
│   ├── webchat.ts          Bot + conversation + public-chat typed client
│   ├── marketing.ts        Marketing Studio typed client + template apply
│   ├── academic.ts         Academic typed client across all 11 sub-modules
│   └── academicRoles.ts    Helpers for student/teacher/registrar/dean role checks
├── i18n/                   react-i18next, en/es/fr/de
└── hooks/
    ├── useOnline.ts
    └── useLicenseFeatures.ts   /license/features query + useHasFeature(name)
```

## Auth flow

```
POST /api/v1/auth/login (email, password)
       │
       ▼
  bcrypt.checkpw → record LoginAttempt → audit log → issue
       │                                              │
       ▼                                              ▼
  JWT access (HS256, 1h)             JWT refresh (HS256, 14d)
  → returned in body                  → bcrypt-hashed in refresh_tokens table
       │                                              │
       ▼                                              ▼
  Authorization: Bearer …            POST /api/v1/auth/refresh
                                       → match against stored hashes
                                       → rotate (revoke old, issue new)
```

Roles split into two tiers:

- **Platform roles** (every install): `Admin > Manager > Developer > Employee`.
  Used by `require_roles(...)` to guard write endpoints across finance, HR,
  CRM, projects, inventory, documents, communication, security, and coding.
- **Academic roles** (EDU SKU only): `Student / Teacher / Registrar / Dean`.
  Used by the academic sub-routers via the `require_any_role(...)` helper in
  `app/api/v1/endpoints/academic/_common.py`. These roles only do anything
  useful when the active license includes the `academic` feature; otherwise
  the academic endpoints return 403 from the plan gate before the role check
  runs.

`get_current_user` accepts either a Bearer token (API / SDK / tests) or the
`access_token` httpOnly cookie set by the login endpoint (browser clients).

## License plan + SKU gating

EnterpriseCore ships every module in one binary; SKUs are enforced at request
time by a thin plan layer. The relevant files:

- `app/core/license_key.py` — HMAC-signed `LICENSE_KEY` parser. Returns a
  `LicenseStatus` (`active` / `expired` / `invalid` / `evaluation` /
  `unverified`) with optional customer, plan, issued_on, expires_on.
- `app/core/plans.py` — defines the `Plan` enum (`evaluation` / `core` / `edu`
  / `verticals`) and the `PLAN_FEATURES` map of plan → feature set. Exposes
  `resolve_plan()` (maps a license payload onto the enum, defaulting to
  `evaluation` for missing / invalid / expired keys) and `has_feature(name)`.
- `app/api/deps.py` — adds `require_plan_feature(name)`, a FastAPI dependency
  that raises `PermissionDenied` when the active plan doesn't include the
  named feature. Combines naturally with `require_roles(...)`.
- `app/api/v1/endpoints/modules.py` — filters `MODULE_CATALOG` from
  `db/init_db.py` by the active plan's feature set, so the nav catalog the
  frontend renders never shows groups the license can't unlock.
- `app/api/v1/endpoints/license.py` — exposes `/license/status` (verification
  result, used for banners) and `/license/features` (resolved plan + feature
  set, used by the frontend on boot to drive nav gating).

The frontend mirrors this on the client side. `frontend/src/hooks/useLicenseFeatures.ts`
queries `/license/features` once per session (5-minute stale time) and
`useHasFeature(name)` returns a boolean the nav and module pages use to
hide / show themselves. The hook returns false while loading so gated UI
never flashes before the plan resolves.

The current feature set per plan:

| Feature              | Evaluation | Core | EDU | Verticals |
|----------------------|:---------:|:----:|:---:|:--------:|
| `webchat`            | yes       | yes  | yes | yes      |
| `marketing`          | yes       | yes  | yes | yes      |
| `marketing_templates`| yes       | yes  | yes | yes      |
| `academic`           | —         | —    | yes | —        |

Everything else — auth, dashboard, settings, finance, hr, crm, projects,
inventory, documents, communication, security, coding, ai brain, knowledge
hub — is always-on platform functionality and is not subject to plan gating.

See `docs/SKU_FEATURES.md` for license issuance and pilot guidance.

## Public-facing routes (not under `/api/v1`)

These routes are mounted directly on the FastAPI app so they live at the
host root and can be embedded / shared without revealing the API surface:

- `GET /widget.js` — static embeddable chat widget. Served from
  `app/static/widget.js` with `Cache-Control: public, max-age=300` and a
  permissive `Access-Control-Allow-Origin: *` so customers can drop a
  single `<script src="https://<host>/widget.js" data-bot-id="...">` tag
  onto any third-party site. The endpoint itself is unauthenticated; it
  only serves the script. Plan gating happens at `/api/v1/webchat/chat/{bot_id}`
  which the widget calls — when the license drops the `webchat` feature the
  widget script still loads but every chat request 403s.
- `GET /site/...` — Jinja2-rendered marketing site. Routes: `/site/`,
  `/site/about`, `/site/services`, `/site/portfolio`, `/site/portfolio/{slug}`,
  `/site/blog`, `/site/blog/{slug}`, `/site/contact`, plus `/site/sitemap.xml`
  and `/site/uploads/{upload_id}` for media files. All routes are gated by
  `require_plan_feature("marketing")` so the public site disappears entirely
  when the marketing feature is disabled. No auth required for visitors;
  responses are cached for 60 seconds (`Cache-Control: public, max-age=60`)
  to absorb traffic bursts without DB churn.

## Data safety

- **Encryption at rest**: password vault entries and webchat BYO API keys are
  Fernet-encrypted with a key derived from `SECRET_KEY` (or a dedicated
  `ENCRYPTION_KEY` if set). Webchat keys are decrypted only when dispatching
  to the AI provider; they never appear in API responses (`has_byo_key` is
  exposed instead).
- **Marketing image uploads** are MIME-checked, capped at 2 MB, re-encoded
  server-side as PNG (strips EXIF + ICC metadata) and downscaled to 1600px
  on the longest side. Upload routes carry a 5/min per-IP throttle so the
  editor can't be used to fill disk.
- **No outbound calls** unless an AI provider key is configured. Ollama runs
  locally.
- **Backups** are AES-style zipped local archives via the Security module
  and cover the marketing / webchat / academic tables along with everything
  else — there is no sidecar database.
- **Audit trail** captures every mutation on finance objects. Marketing
  template applies write a Notification to the operator's bell so the audit
  trail shows who applied which template and when.

## Building the .exe

```powershell
npm run setup           # one-time
npm run build:exe       # produces electron/dist/EnterpriseCore-Setup.exe
```

Alternative: run `iscc installer/inno-setup.iss` after `npm run build` to produce a Inno Setup installer in `dist/`.
