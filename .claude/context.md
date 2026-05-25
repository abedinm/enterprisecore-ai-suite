# EnterpriseCoreAI — context map

> Read this first. It points to the truth instead of forcing greps.

## What this is

Offline-first business management + AI coding assistant. 130-module ambition. Single-payment desktop app packaged as a Windows .exe (NSIS). Stack: FastAPI + SQLAlchemy + React + Vite + TS + Tailwind + Electron + PyInstaller.

## Entry points

| File | What |
|---|---|
| `backend/app/main.py` | FastAPI app + lifespan + router mount (447 routes) |
| `backend/runserver.py` | Frozen-bundle uvicorn entry (reads `BACKEND_PORT`) |
| `backend/app/api/v1/router.py` | All `/api/v1/*` route mounts |
| `frontend/src/App.tsx` | React route table — module pages live in `src/pages/<module>/` |
| `electron/main.js` | Desktop wrapper — spawns backend sidecar, opens window |
| `electron/preload.js` | IPC bridge (vault, dialogs, backend URL) |

## Build & test

| Command | What |
|---|---|
| `make test` | pytest (206 tests; ~30s) |
| `make test-frontend` | tsc + vite build |
| `make dev` | uvicorn :8765 + Vite :5173 in parallel |
| `npm run build:exe` | frontend → pyinstaller backend → stage → electron-builder NSIS |

## Module shape (backend)

For every business module (`finance`, `hr`, `crm`, `projects`, `inventory`, `documents`, `communication`, `security`, `coding`, `ai`, `knowledge`):

- `app/models/<m>.py` — SQLAlchemy ORM
- `app/schemas/<m>.py` — pydantic in/out
- `app/api/v1/endpoints/<m>.py` — FastAPI routes
- `app/services/<m>.py` — business logic + AI calls

## Module shape (frontend)

- `src/pages/<m>/<M>Page.tsx` — tab shell
- `src/pages/<m>/<Tab>Tab.tsx` — per-feature panels
- shared UI in `src/components/`
- API client in `src/lib/api.ts` (axios + JWT refresh interceptor)

## Conventions

- **Money**: Decimal cents, currency = ISO 4217
- **Time**: UTC stored, locale-rendered
- **Roles**: Admin / Manager / Developer / Employee (`app/core/security.py`)
- **AI**: Anthropic + OpenAI + Ollama (`app/services/ai.py`) with cost tracking and auto-fallback
- **Alembic**: migrations must be idempotent (use `_has_column` helpers)
- **Tests**: shared `conftest.py` in `backend/tests/`; SQLite in-memory by default

## Migration chain

```
0001_initial → 0002_rename_pluralized → 0003_ai_coding_module
→ 0004_pm_inventory_expansion → 0005_audit_detail_json
→ 0006_knowledge_hub → 0007_user_mfa
```

## Gotchas

- **`BUILD_STATUS.md` can lag reality.** Trust code + tests over docs.
- **Don't run `npm install` in `electron/` casually** — pulls 500+ MB.
- **PyInstaller `--onefile` extracts to `%TEMP%\_MEI*`** every launch. Smoke-test cleanup matters.
- **Pre-extract `winCodeSign-2.6.0.7z` without `darwin/`** — see [desktop-build-notes](../../../C:/Users/USER/.claude/projects/F--/memory/desktop_build_notes.md).
- **The frontend dist must go in `extraResources`, not `files`** — was silently dropped from asar before the fix.

## Memory pointers

- Project memory: `~/.claude/projects/F--/memory/project_enterprisecore.md`
- Knowledge Hub build: `knowledge_hub_build.md`
- Build pipeline: `desktop_build_notes.md`

## Active TODO

- Sign the installer (need code-signing cert)
- End-to-end smoke through the packaged .exe on a clean VM
- Inno Setup alternative (script already at `installer/inno-setup.iss`)
- Auto-updater feed hosting
