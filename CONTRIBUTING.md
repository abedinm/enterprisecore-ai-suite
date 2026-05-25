# Contributing to EnterpriseCore AI Suite

Thanks for taking the time to contribute. This guide covers what you need to
know to get a working dev environment, ship a quality patch, and have it
accepted.

## Project overview

EnterpriseCore AI Suite is a fully offline-capable business management +
AI coding suite. Three first-class deliverables ship from this monorepo:

- **Backend** — FastAPI (Python 3.13), SQLAlchemy 2.x, packaged via PyInstaller
- **Frontend** — React 18 + TypeScript + Vite + Tailwind CSS
- **Desktop wrapper** — Electron + electron-builder (NSIS / DMG / AppImage)

For deeper background, read:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/CONSOLIDATION_PLAN.md`](docs/CONSOLIDATION_PLAN.md)
- [`docs/SKU_FEATURES.md`](docs/SKU_FEATURES.md)
- [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md)

## Local setup

Clone, then from the repo root:

```bash
# One-shot setup (Windows-style; adapt python/.venv path for *nix)
npm run setup

# Or do it manually:
cd backend && python -m venv .venv
.venv/Scripts/pip install -r requirements.txt -r requirements-dev.txt

cd ../frontend && npm install
cd ../electron && npm install
```

Required tooling:

- Python 3.13
- Node 20 LTS
- A C/C++ build chain for native node modules (Visual Studio Build Tools on
  Windows, Xcode CLT on macOS, `build-essential` on Linux)

## Running locally

```bash
# Backend + frontend together
npm run dev

# Backend only (port 8765)
npm run dev:backend

# Frontend only (port 5173)
npm run dev:frontend

# Desktop wrapper (assumes backend + frontend are running)
npm run dev:electron
```

## Running tests

```bash
# Backend
cd backend
pytest -q                                   # quick
pytest -v --cov=app --cov-report=term       # with coverage
pytest tests/test_finance.py -k invoices    # one file, one keyword

# Frontend
cd frontend
npm test                                    # vitest, one-shot
npm run test:watch                          # vitest, watch mode

# E2E (Playwright — once configured)
cd frontend
npm run test:e2e
```

The CI gate is `pytest -q` passing + coverage at or above 70% on changed code.

## Code style

| Language   | Tool       | Command                          |
|------------|------------|----------------------------------|
| Python     | ruff       | `ruff check backend/app backend/tests` |
| Python     | black      | `black backend/app backend/tests`      |
| Python     | mypy       | `mypy backend/app --ignore-missing-imports` |
| TypeScript | eslint     | `cd frontend && npm run lint`    |
| TypeScript | prettier   | `cd frontend && npx prettier --write src` |

**Hard rules** (enforced or strongly preferred):

- No emojis in code, commit messages, PR titles, or filenames.
- 4-space indent for Python, 2-space for everything else.
- LF line endings, UTF-8, final newline, trim trailing whitespace.
  See [`.editorconfig`](.editorconfig).
- Money as `Decimal` with cents precision. Timestamps in UTC. Currency as
  ISO 4217 codes.
- Alembic migrations must be idempotent — safe to re-run.

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

[optional body]

[optional footer]
```

Allowed types:

- `feat` — new feature
- `fix` — bug fix
- `chore` — tooling, deps, build config (no user-visible change)
- `docs` — documentation only
- `test` — test-only changes
- `refactor` — code change that neither fixes a bug nor adds a feature
- `perf` — performance improvement
- `ci` — CI/CD changes
- `revert` — reverts a prior commit

Examples:

```
feat(finance): add multi-currency journal entries
fix(auth): reject expired refresh tokens before deserializing payload
chore(deps): bump fastapi 0.115 -> 0.116
docs(architecture): document module boundary rules
```

Keep the subject under 70 characters, in the imperative mood, lowercase, no
trailing period.

## Pull request process

1. **Branch off `main`.** Use a short topical name: `feat/multi-currency`,
   `fix/auth-refresh-bug`.
2. **Keep the diff small.** Aim for under 500 changed lines per PR. Bigger
   diffs need a heads-up in `#engineering` (or your team's equivalent).
3. **Tests are required** for new behavior. Bug fixes need a regression test
   that fails before your fix and passes after.
4. **Run the full test suite locally** before opening the PR.
5. **Fill in the PR template.** Explain the why, not just the what.
6. **Mark draft early.** Open as draft if you want feedback on direction
   before polishing.
7. **One reviewer minimum.** Two for cross-cutting changes (database schema,
   auth, billing). CODEOWNERS will be requested automatically.
8. **Resolve conversations** before merging. Squash-merge is the default.

## Issues

File issues with:

- A clear title in `[area] short description` form (`[finance] invoice total
  off by 1 cent on multi-line discount`).
- Steps to reproduce, expected behavior, actual behavior.
- Version (commit SHA or installer build number) and OS.

Security issues: do **not** file a public issue. Follow the disclosure path in
`SECURITY.md`.

## License

By contributing, you agree your contributions will be licensed under the same
proprietary license as the rest of this repository
([`docs/LICENSE.txt`](docs/LICENSE.txt)).
