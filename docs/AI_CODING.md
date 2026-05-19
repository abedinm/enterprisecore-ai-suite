# AI Coding Assistant — User Guide

EnterpriseCore ships a **15-tool, VS-Code-style coding assistant** built into
the desktop suite. It runs **fully offline** (no auth/data ever leaves the
machine) and lets you bring your own Claude or OpenAI key for the AI calls.

---

## 1. The 15 tools

| # | Tool | Where it lives | Key files |
|---|------|-----------------|-----------|
| 1 | Monaco editor (60+ languages) | center pane | `frontend/src/pages/coding/EditorTabs.tsx` |
| 2 | File tree / project explorer | left pane | `FileTree.tsx`, `CodingPage.tsx` |
| 3 | Integrated terminal (xterm.js + sandboxed allow-list) | right rail → Terminal | `panels/TerminalPanel.tsx`, backend `coding.py::_safe_argv` |
| 4 | AI chat — Claude / OpenAI / Ollama switch | right rail → AI Chat | `panels/ChatPanel.tsx` |
| 5 | Code generation from plain English | right rail → AI Tools → Generate | `panels/CodeToolsPanel.tsx`, `/coding/ai/generate` |
| 6 | Explanation + docstring generator | AI Tools → Explain / Docs | `/coding/ai/explain`, `/coding/ai/docstring` |
| 7 | Bug detector + auto-fixer (Monaco diff + Apply) | AI Tools → Bug Fix | `/coding/ai/bugfix` |
| 8 | Code review (line-level findings) | AI Tools → Review | `/coding/ai/review` |
| 9 | Multi-file AI edits (plan → review diff → apply) | right rail → Multi-file | `panels/MultiFilePanel.tsx`, `/coding/ai/multi-file-plan`, `/multi-file-apply` |
| 10 | Git (status, diff, commit, push, pull, branches) | right rail → Git | `panels/GitPanel.tsx` |
| 11 | Syntax highlighting (60+ languages) | Monaco theme + `_detect_language` | `coding.py::LANGUAGE_BY_EXT`, `/coding/languages` |
| 12 | Snippet library | right rail → Snippets | `panels/SnippetsPanel.tsx`, `/coding/snippets` |
| 13 | Postman-style API tester | right rail → API Tester | `panels/ApiTesterPanel.tsx` |
| 14 | DB query builder + visualizer (NL → SQL, schema browser, paged results) | right rail → DB Query | `panels/DbPanel.tsx` |
| 15 | Regex builder with AI explain + AI build | right rail → Regex | `panels/RegexPanel.tsx` |

---

## 2. Quickstart

### Development mode (hot reload)

```powershell
# backend
cd F:\EnterpriseCoreAI\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8765

# frontend
cd F:\EnterpriseCoreAI\frontend
npm install
npm run dev

# desktop wrapper (optional — points at the dev servers)
cd F:\EnterpriseCoreAI\electron
npm install
npm run dev   # sets ELECTRON_DEV=1
```

Visit <http://127.0.0.1:5173>, sign in as `admin@local` / `ChangeMe123!`,
and click **AI Coding** in the left sidebar.

### Adding your first project

1. Click **+** next to *Projects* in the left rail
2. Either paste an absolute path or — in the desktop app — click **Browse…**
3. The file tree appears immediately. `.git`, `node_modules`, `__pycache__`,
   `dist`, `build`, etc. are auto-hidden.

---

## 3. Bringing your own API key (BYO key)

The right rail has a **Keys** tab. Paste your key once; it is stored:

- **Desktop**: encrypted via Electron `safeStorage` — which uses the OS-level
  vault (Windows DPAPI, macOS Keychain, libsecret on Linux). The file lives
  in `app.getPath('userData')/vault/credentials.enc` with mode `0600`.
- **Web fallback**: localStorage on the current browser only. The Keys panel
  shows which mode is active.

The key is **never persisted server-side**. On each AI call, the frontend
attaches it as `api_key_override` in the request body and the backend passes
it directly to the provider's SDK.

If you don't supply a key and the server has none configured either, the
backend falls back to a local Ollama daemon at `http://127.0.0.1:11434` —
free, fully local, no signup. Recommended local model:
`ollama pull qwen2.5-coder`.

---

## 4. Terminal sandbox

The terminal is **NOT** a free-form shell. It runs **one** command with
`shell=False` and only allows executables on the allow-list:

```
python python3 pip pip3 pipx uv poetry
node npm npx yarn pnpm bun
git make cargo go mvn gradle dotnet rake
pytest tox jest vitest mocha phpunit
ruff black isort mypy pylint flake8 eslint prettier tsc rustfmt gofmt
ls dir pwd cat type head tail wc find where grep rg ack ag tree
stat du df file echo printf
```

It rejects:

- shell metacharacters `& | ; > < ` $() backticks newlines`
- destructive verbs (`rm`, `del`, `mkfs`, `dd`, `shutdown`, …)
- working directories outside the project root (path-traversal guard)

Use the `cd folder` built-in to change directory inside a session, and
`clear`/`cls` to wipe the screen. History is `↑/↓` arrow keys; `Ctrl+C`
clears the current line, `Ctrl+L` clears the buffer.

If you want to run shell pipelines (`a && b`), break them into two
sequential calls or wrap them in a script and run the script.

---

## 5. Multi-file AI editing

The Multi-file panel lets the AI rewrite several files in lockstep:

1. Type a natural-language change request
2. Mark **context files** (read-only, used as background) and **target files**
   (may be modified — can include files that don't exist yet)
3. Click **Plan multi-file change**. The AI returns full new contents for each
   target file.
4. Each change appears as a side-by-side Monaco diff with a check box. Untick
   anything you don't want. Click **Apply selected** to write.

This sends one `/coding/ai/multi-file-plan` call (which never writes anything)
followed by an explicit `/coding/ai/multi-file-apply` (which the backend
guards behind the developer/admin/manager role).

---

## 6. DB query builder

The DB panel manages connections to your own databases:

- **Postgres**: `postgresql+psycopg2://user:pass@host:5432/db`
- **MySQL**: `mysql+pymysql://user:pass@host:3306/db`
- **SQLite**: `sqlite:///F:/data/file.db`
- **MSSQL**: `mssql+pyodbc://user:pass@host/db?driver=ODBC+Driver+17+for+SQL+Server`

The DSN is encrypted at rest with Fernet (`backend/app/core/security.py::encrypt_text`).

After connecting, the **Schema browser** shows tables, columns, PK / FK
constraints. Click a column / table name to drop a `SELECT * FROM …` into the
SQL editor. Hit **Run query** to execute (paged to 500 rows; mutations are
allowed since this is a user-owned connection).

You can also describe a query in English ("top 10 customers by revenue last
quarter") and the **NL → SQL** button feeds the active connection's schema as
hint context to the AI.

---

## 7. Regex builder

- Edit pattern + flags inline (Python flags: `i`, `m`, `s`, `x`, `a`, `u`).
- Sample text is re-tested live (300 ms debounce); matches are highlighted.
- Replacement preview supports back-references (`\1`, `\g<name>`).
- **Explain current pattern** asks the AI for a step-by-step plain-English
  walkthrough plus 3-5 illustrative inputs.
- **Build regex from description** takes a goal + positive/negative examples
  and returns a tested pattern.
- Save common patterns to the per-user library for one-click recall.

---

## 8. API tester (Postman-style)

Saved requests are organised into **collections**. Each request stores method,
URL, headers, query params, and body. The response pane renders pretty JSON
with content-type detection (JSON / XML / HTML / plaintext).

The execute endpoint follows redirects, times out at 60 s max, and returns
both headers and body to the panel.

---

## 9. Architecture summary

```
   ┌──────────────────────────────┐
   │     Electron (preload.js)    │
   │  safeStorage vault + menus   │
   └─────────────┬────────────────┘
                 │ IPC
   ┌─────────────▼────────────────┐
   │  React frontend (CodingPage) │
   │  Monaco · xterm.js · panels  │
   └─────────────┬────────────────┘
                 │ axios → /api/v1/coding/*
   ┌─────────────▼────────────────┐
   │     FastAPI backend          │
   │  60+ routes · path jail      │
   │  sandboxed terminal          │
   │  GitPython · SQLAlchemy      │
   │  Fernet (DSN, secrets)       │
   └─────────────┬────────────────┘
                 │
   ┌─────────────▼────────────────┐
   │  AI dispatcher (ai_svc.call) │
   │  anthropic │ openai │ ollama │
   │  BYO api_key_override        │
   │  usage / cost / spend-cap    │
   └──────────────────────────────┘
```

### REST surface (selected)

```
GET    /api/v1/coding/projects
POST   /api/v1/coding/projects
DELETE /api/v1/coding/projects/{id}
GET    /api/v1/coding/tree            ?project_id=&depth=
GET    /api/v1/coding/file            ?project_id=&path=
POST   /api/v1/coding/file            (body: path, content)
DELETE /api/v1/coding/file            ?project_id=&path=
POST   /api/v1/coding/file/new        ?project_id=&path=&is_dir=
POST   /api/v1/coding/file/rename     ?project_id=&old_path=&new_path=
GET    /api/v1/coding/search-in-files ?project_id=&query=

POST   /api/v1/coding/terminal        ?project_id=

GET    /api/v1/coding/git/status      ?project_id=
POST   /api/v1/coding/git/stage|unstage|commit|checkout|push|pull|init
GET    /api/v1/coding/git/log|diff|branches

GET    /api/v1/coding/snippets
POST   /api/v1/coding/snippets, PUT /…/{id}, DELETE /…/{id}
POST   /api/v1/coding/snippets/{id}/use
POST   /api/v1/coding/snippets/suggest    (AI)

GET    /api/v1/coding/api-requests
POST   /api/v1/coding/api-requests, PUT/DELETE /…/{id}
POST   /api/v1/coding/api-tester/execute

POST   /api/v1/coding/ai/chat
POST   /api/v1/coding/ai/generate
POST   /api/v1/coding/ai/explain
POST   /api/v1/coding/ai/docstring
POST   /api/v1/coding/ai/bugfix
POST   /api/v1/coding/ai/review
POST   /api/v1/coding/ai/multi-file-plan
POST   /api/v1/coding/ai/multi-file-apply
POST   /api/v1/coding/ai/db-query

GET    /api/v1/coding/db/connections
POST   /api/v1/coding/db/connections, DELETE /…/{id}
GET    /api/v1/coding/db/connections/{id}/schema
POST   /api/v1/coding/db/execute

POST   /api/v1/coding/regex/test
POST   /api/v1/coding/regex/explain          (AI)
POST   /api/v1/coding/regex/from-description (AI)
GET    /api/v1/coding/regex/library
POST   /api/v1/coding/regex/library, DELETE /…/{id}

GET    /api/v1/coding/languages
```

---

## 10. Database migrations

The schema for the coding/AI module is in two Alembic revisions:

- `0001_initial.py` — baseline (snapshots `Base.metadata.create_all`)
- `0003_ai_coding_module.py` — adds `regex_library_entries`, `database_connections`,
  and brings older `code_projects` / `code_snippets` / `api_requests` /
  `ai_conversations` / `ai_messages` / `ai_usage_records` / `chatbots` /
  `chatbot_messages` rows in line with the BYO-key-aware ORM.

The migration is **idempotent** — it inspects the live DB and only applies
the deltas that haven't been applied yet, so it's safe on both fresh installs
and upgraded ones.

```powershell
cd F:\EnterpriseCoreAI\backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

The application also self-heals on startup via `init_db()` which runs
`Base.metadata.create_all` for any tables the migration history doesn't know
about.

---

## 11. Testing

```powershell
cd F:\EnterpriseCoreAI\backend
.\.venv\Scripts\python.exe -m pytest tests/test_coding.py -p no:cacheprovider -q
```

The coding suite covers 29 cases: project lifecycle, file tree + traversal
guard, terminal sandbox rejections, git init/status, snippet CRUD, regex
matching (matches / replacement / invalid pattern / flags), regex library,
DB connection + introspection + execute against a real SQLite, full AI
pipeline with mocked providers (generate / explain / docstring / bugfix /
review / db-query / multi-file plan + apply / regex explain / regex build),
and the 60+ language listing.

The frontend type-checks with `npx tsc --noEmit` and bundles with
`npx vite build` (2,432 modules, 9 s, gzipped main 148 KB).

---

## 12. Troubleshooting

| Symptom | Fix |
|---------|-----|
| "Anthropic / OpenAI API key not configured" | Open **Keys** in the right rail and paste yours, or start a local Ollama daemon |
| Terminal rejects `npm install && npm run build` | Run them as two separate commands (the sandbox does not expand `&&`) |
| Multi-file apply says "AI did not return valid JSON" | Lower the prompt scope or retry; large prompts sometimes overflow the AI's output window |
| Git push fails with auth error | Configure credential.helper in your global git config — the sandbox doesn't prompt for passwords |
| `git push --force` is blocked | The dependency guard rejects only destructive shell verbs, not git arguments — but the desktop app's git layer requires you to push manually for force-push to use the system credentials store |
| Database query times out | Reduce `limit` or rewrite the query — the DB executor caps results at 5,000 rows |

---

That's it. The module is offline-first, BYO-key, and every tool has a real
working implementation — no placeholders.
