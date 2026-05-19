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
   │   - 18 module APIs  │ +-token │  - Monaco IDE            │
   │   - SQLAlchemy ORM  │         │  - 130+ tools UIs        │
   │   - Ollama/Claude   │         │  - i18n (4 languages)    │
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
├── main.py                 FastAPI app, lifespan, CORS, static files
├── core/
│   ├── config.py           pydantic-settings, env-driven
│   ├── security.py         bcrypt, JWT (HS256), Fernet encryption
│   ├── exceptions.py       Typed app errors + global handlers
│   └── logging.py          Loguru with file rotation
├── db/
│   ├── session.py          SQLAlchemy engine, SQLite PRAGMAs
│   ├── base.py             Declarative base, IdMixin, TimestampMixin
│   └── init_db.py          create_all + seed admin + module catalog
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
│   └── ai.py               AiConversation, AiMessage, AiUsageRecord, Chatbot…
├── schemas/                One file per module — pydantic request/response models
├── services/               Business logic that's heavier than a CRUD route
│   ├── audit.py            Centralized audit logging
│   ├── finance.py          Invoice math, P&L, balance sheet, cash flow, forecast, PDF
│   └── ai.py               Multi-provider AI calls with cost tracking
└── api/
    ├── deps.py             get_db, get_current_user, require_roles
    └── v1/
        ├── router.py       Aggregates all module routers
        └── endpoints/      One file per module
            ├── auth.py           login/register/refresh/me/password
            ├── users.py          admin user management
            ├── dashboard.py      KPI rollup across modules
            ├── settings.py       global config kv store
            ├── notifications.py  in-app alerts
            ├── search.py         cross-module text search
            ├── modules.py        feature catalog
            ├── finance.py        15+ tools, 40+ routes
            ├── hr.py
            ├── crm.py
            ├── projects.py
            ├── inventory.py
            ├── documents.py
            ├── communication.py
            ├── security_mod.py
            ├── coding.py         + AI codegen/review/bugfix
            └── ai.py             + chatbot builder, smart search
```

## Frontend layout

```
frontend/src/
├── main.tsx, App.tsx       Router, QueryClient, theme bootstrap
├── components/layout/
│   └── AppShell.tsx        Sidebar nav, header, online/offline badge
├── pages/
│   ├── auth/               Login, Register
│   ├── dashboard/          KPI home
│   ├── search/             Global search UI
│   ├── settings/           Configuration grid
│   ├── finance/            15 tabs (Invoices, P&L, Cash Flow, etc.)
│   ├── coding/             Monaco IDE + AI chat + Terminal + Git panel
│   └── ModulePage.tsx      Generic placeholder for modules not yet UI-implemented
├── store/
│   ├── auth.ts             Zustand store w/ token refresh
│   └── theme.ts            Light/dark/system
├── lib/
│   ├── api.ts              Axios client + interceptors + token store
│   └── utils.ts            Currency/date formatters, cn()
├── i18n/                   react-i18next, en/es/fr/de
└── hooks/                  useOnline, etc.
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

Roles: `admin > manager > developer > employee`. `require_roles(...)` dependency
guards write endpoints; read endpoints stay open to authenticated users.

## Data safety

- **Encryption at rest**: password vault entries are Fernet-encrypted with a key derived from `SECRET_KEY` (or a dedicated `ENCRYPTION_KEY` if set).
- **No outbound calls** unless an AI provider key is configured. Ollama runs locally.
- **Backups** are AES-style zipped local archives via the Security module.
- **Audit trail** captures every mutation on finance objects.

## Building the .exe

```powershell
npm run setup           # one-time
npm run build:exe       # produces electron/dist/EnterpriseCore-Setup.exe
```

Alternative: run `iscc installer/inno-setup.iss` after `npm run build` to produce a Inno Setup installer in `dist/`.
