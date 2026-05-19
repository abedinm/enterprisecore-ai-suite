# EnterpriseCore AI Suite

> Replace every software subscription your company pays for — with one payment, your data never leaves your building, and it works even without internet.

## Two pillars

1. **Enterprise Business Suite** — Finance, HR, CRM, Projects, Inventory, Documents, Communication, Security (90+ tools)
2. **AI Coding Assistant** — Monaco-based IDE with Claude/OpenAI/Ollama chat (15+ tools)

## Architecture

| Layer | Tech |
|---|---|
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| Backend | FastAPI (Python 3.11+) + SQLAlchemy 2.x |
| DB | SQLite (default, offline) / PostgreSQL (optional, multi-user) |
| Desktop | Electron + electron-builder |
| Installer | NSIS (.exe) via electron-builder, Inno Setup alt |
| AI | Anthropic API + OpenAI API + Ollama (local) |
| Auth | JWT (HS256) + bcrypt |
| Editor | Monaco Editor |
| PDF | ReportLab |
| Charts | Recharts |
| Git | GitPython |

## Quick start (development)

```powershell
# Install everything
npm run setup

# Start backend + frontend together
npm run dev

# Build production .exe
npm run build:exe
```

Open http://localhost:5173 (web) — desktop launches automatically when running `npm run dev:electron`.

## Project layout

```
EnterpriseCoreAI/
├── backend/              FastAPI app
│   ├── app/
│   │   ├── api/v1/       Versioned REST endpoints (one router per module)
│   │   ├── core/         config, security, deps, exceptions
│   │   ├── db/           SQLAlchemy session, base
│   │   ├── models/       ORM models (one file per module group)
│   │   ├── schemas/      Pydantic request/response models
│   │   ├── services/     Business logic (calculators, generators)
│   │   └── utils/        PDF, crypto, i18n, etc.
│   ├── alembic/          DB migrations
│   ├── storage/          Local file storage (uploads, backups, reports)
│   └── tests/
├── frontend/             React + Vite
│   ├── src/
│   │   ├── pages/        One subfolder per module
│   │   ├── components/   layout/, ui/, charts/
│   │   ├── lib/          api client, helpers
│   │   ├── hooks/
│   │   ├── store/        Zustand stores
│   │   └── i18n/
├── electron/             Desktop wrapper
├── installer/            Inno Setup script
├── docs/                 User & developer docs
└── scripts/              dev helpers
```

## Default admin

On first run the backend seeds:

| Email | Password | Role |
|---|---|---|
| admin@local | `ChangeMe123!` | Admin |

**Change this immediately.**

## License

Proprietary — license key activation required for production builds.
