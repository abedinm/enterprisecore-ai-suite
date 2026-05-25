# EnterpriseCore AI Suite

[![ci](https://img.shields.io/badge/build-pending-lightgrey)](.github/workflows/ci.yml)
[![tests](https://img.shields.io/badge/tests-481%20passing-brightgreen)](backend/tests)
[![coverage](https://img.shields.io/badge/coverage-70%25%2B-brightgreen)](.github/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-Proprietary-blue)](docs/LICENSE.txt)
[![SKUs](https://img.shields.io/badge/SKUs-Core%20%7C%20%2BEDU%20%7C%20%2BVerticals-orange)](docs/SKU_FEATURES.md)

> Replace every software subscription your company pays for — with one
> payment, your data never leaves your building, and it works even without
> internet.

EnterpriseCore AI Suite is an offline-capable business management and AI
coding platform built as a single Electron desktop application. It bundles a
130-module FastAPI backend, a React + TypeScript frontend, and a full Monaco
IDE with multi-provider AI assistance (Claude, OpenAI, local Ollama) — all
deployable as a single signed installer that runs without internet access.

## Two pillars

1. **Enterprise Business Suite** — Finance, HR, CRM, Projects, Inventory,
   Documents, Communication, Security (90+ tools)
2. **AI Coding Assistant** — Full Monaco IDE with Claude / OpenAI / Ollama
   chat (15 tools, all functional)

### AI Coding Assistant — the 15 tools

| # | Tool | Highlights |
|---|------|-----------|
| 1 | Monaco editor | Tabs, dirty state, ligatures, multi-cursor, 60+ languages |
| 2 | Project explorer + file tree | New / rename / delete, `node_modules` hidden, traversal-guarded |
| 3 | Integrated terminal | xterm.js, sandboxed allow-list (python/node/git/...), ANSI colors, history |
| 4 | AI chat | Provider switcher (Claude / OpenAI / Ollama), context-file chips, markdown |
| 5 | Code generation | Prompt to fenced code + explanation |
| 6 | Explain + Docstrings | Google / NumPy / Sphinx / JSDoc; diff preview |
| 7 | Bug detector + auto-fixer | Stack-trace input, Monaco diff, one-click apply |
| 8 | Code review | Severity-tagged findings with line numbers and suggestions |
| 9 | Multi-file AI edit | AI plan, per-file diff approval, apply |
| 10 | Git integration | Status, stage, commit, push, pull, branches, diff viewer |
| 11 | Syntax highlighting | 60+ languages via `/coding/languages` registry |
| 12 | Snippet library | CRUD, tags, public/private, AI suggest |
| 13 | API tester | Postman-style collections, KV editors, response viewer |
| 14 | DB query builder + visualizer | NL to SQL, schema browser, paged results, encrypted DSN |
| 15 | Regex builder | Live tester, AI explain, AI build-from-description, library |

**BYO API keys** — paste your Claude or OpenAI key once; it is stored in your
OS credential vault via Electron `safeStorage` (Windows DPAPI / macOS
Keychain / libsecret on Linux). Keys are passed per-call as
`api_key_override`, never persisted server-side. With no key, the suite falls
back to a local Ollama daemon.

See [`docs/AI_CODING.md`](docs/AI_CODING.md) for the full guide and
[`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) for the complete feature index.

## Tech stack

| Layer | Tech |
|---|---|
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| Backend | FastAPI (Python 3.13+) + SQLAlchemy 2.x |
| DB | SQLite (default, offline) / PostgreSQL (optional, multi-user) |
| Desktop | Electron + electron-builder |
| Installer | NSIS / Squirrel.Windows (Win), DMG + universal (mac), AppImage + deb + rpm (Linux) |
| AI | Anthropic API + OpenAI API + Ollama (local) |
| Auth | JWT (HS256) + bcrypt |
| Editor | Monaco Editor |
| PDF | ReportLab |
| Charts | Recharts |
| Git | GitPython |

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full diagram and
module boundary rules.

## Quick start

### Install the binary

Download the latest installer for your platform from the
[Releases page](../../releases):

- Windows: `EnterpriseCore AI Suite-Setup-<version>-x64.exe`
- macOS: `EnterpriseCore AI Suite-<version>-universal.dmg`
- Linux: `.AppImage`, `.deb`, or `.rpm`

Run the installer, launch the app, and sign in with the seeded admin
account (see below).

### Run from source (development)

```powershell
# One-shot install (backend venv + frontend npm + electron npm)
npm run setup

# Start backend + frontend together
npm run dev

# Build production .exe (Windows)
npm run build:exe
```

Web UI at http://localhost:5173; backend at http://localhost:8765. The
Electron wrapper auto-launches via `npm run dev:electron`.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full setup, test, and
contribution guide.

## Default admin

On first run the backend seeds:

| Email | Password | Role |
|---|---|---|
| admin@local | `ChangeMe123!` | Admin |

**Change this immediately.**

## SKUs

| SKU | Includes |
|---|---|
| **Core** | 90+ business tools + AI coding assistant |
| **+EDU** | Core + 11 student-focused modules (attendance, CGPA, deadlines, exams, group projects, lab reports, notes, ...) |
| **+Verticals** | Core + restaurant (Corner Table), engineering consultancy (Deltadutch), Bangladesh-ops (Deltadesh), multilingual chat widget (LinguaBot) |

Full feature matrix in [`docs/SKU_FEATURES.md`](docs/SKU_FEATURES.md).

## Releasing

Releases are tag-driven. See [`docs/RELEASE_PROCESS.md`](docs/RELEASE_PROCESS.md)
for the full process.

```bash
# Cut a release
git tag v0.6.0
git push origin v0.6.0
# CI builds + signs + publishes installers
```

## Project layout

```
EnterpriseCoreAI/
  backend/              FastAPI app (Python 3.13)
    app/
      api/v1/           Versioned REST endpoints
      core/             config, security, deps, exceptions
      db/               SQLAlchemy session, base
      models/           ORM models
      schemas/          Pydantic request/response models
      services/         Business logic
      utils/            PDF, crypto, i18n, ...
    alembic/            DB migrations
    storage/            Local file storage
    tests/              pytest suite (481 passing)
  frontend/             React + Vite
    src/
      pages/            One subfolder per module
      components/       layout/, ui/, charts/
      lib/              api client, helpers
      hooks/
      store/            Zustand stores
      i18n/
  electron/             Desktop wrapper + electron-builder config
  installer/            Inno Setup alt script
  docs/                 User & developer docs
  scripts/              Dev helpers
  .github/              CI/CD workflows + Dependabot + CODEOWNERS
```

## Security

See [`SECURITY.md`](SECURITY.md) for the security policy and disclosure
contact. Do not file public issues for security bugs.

## License

Proprietary — see [`docs/LICENSE.txt`](docs/LICENSE.txt). License key
activation is required for production builds.
