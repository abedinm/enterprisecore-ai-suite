# EnterpriseCore AI Suite

> Replace every software subscription your company pays for — with one payment, your data never leaves your building, and it works even without internet.

## Two pillars

1. **Enterprise Business Suite** — Finance, HR, CRM, Projects, Inventory, Documents, Communication, Security (90+ tools)
2. **AI Coding Assistant** — Full Monaco IDE with Claude / OpenAI / Ollama chat (15 tools, all functional)

### AI Coding Assistant — the 15 tools

| # | Tool | Highlights |
|---|------|-----------|
| 1 | Monaco editor | Tabs, dirty state, ligatures, multi-cursor, 60+ languages |
| 2 | Project explorer + file tree | New / rename / delete, `node_modules` hidden, traversal-guarded |
| 3 | Integrated terminal | xterm.js, sandboxed allow-list (python/node/git/…), ANSI colors, history |
| 4 | AI chat | Provider switcher (Claude / OpenAI / Ollama), context-file chips, markdown |
| 5 | Code generation | Prompt → fenced code + explanation |
| 6 | Explain + Docstrings | Google / NumPy / Sphinx / JSDoc; diff preview |
| 7 | Bug detector + auto-fixer | Stack-trace input, Monaco diff, one-click apply |
| 8 | Code review | Severity-tagged findings with line numbers and suggestions |
| 9 | Multi-file AI edit | AI plan → per-file diff approval → apply |
| 10 | Git integration | Status, stage, commit, push, pull, branches, diff viewer |
| 11 | Syntax highlighting | 60+ languages via `/coding/languages` registry |
| 12 | Snippet library | CRUD, tags, public/private, AI suggest |
| 13 | API tester | Postman-style collections, KV editors, response viewer |
| 14 | DB query builder + visualizer | NL → SQL, schema browser, paged results, encrypted DSN |
| 15 | Regex builder | Live tester, AI explain, AI build-from-description, library |

**BYO API keys** — paste your Claude or OpenAI key once; it's stored in your OS
credential vault via Electron `safeStorage` (Windows DPAPI / macOS Keychain /
libsecret on Linux). Keys are passed per-call as `api_key_override`, never
persisted server-side. With no key, the suite falls back to a local Ollama daemon.

See [`docs/AI_CODING.md`](docs/AI_CODING.md) for the full guide.

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
