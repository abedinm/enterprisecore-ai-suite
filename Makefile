# EnterpriseCore AI Suite — developer convenience commands.
#
# Works with GNU make on macOS/Linux and with mingw32-make / Git Bash on
# Windows. The backend lives in ./backend (Python 3.13 + uv-managed .venv)
# and the frontend lives in ./frontend (Node 20+ + Vite).

PY        := backend/.venv/Scripts/python.exe
ifeq (,$(wildcard $(PY)))
PY        := backend/.venv/bin/python
endif

NPM       := npm --prefix frontend
PYTEST    := $(PY) -m pytest
ALEMBIC   := $(PY) -m alembic

.PHONY: help dev backend frontend test test-backend test-frontend lint lint-backend lint-frontend build migrate seed reindex db-shell install install-backend install-frontend clean check

help:  ## Show this help
	@echo "EnterpriseCore AI Suite — make targets"
	@echo
	@awk 'BEGIN{FS=":.*?## "} /^[a-zA-Z0-9_-]+:.*?## /{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ----- run --------------------------------------------------------------
dev:  ## Run backend (uvicorn) and frontend (vite) in parallel
	@echo "==> Starting backend on http://127.0.0.1:8765 and frontend on http://localhost:5173"
	@$(MAKE) -j 2 backend frontend

backend:  ## Run only the backend in dev mode
	cd backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload

frontend:  ## Run only the frontend dev server
	$(NPM) run dev

# ----- test -------------------------------------------------------------
test: test-backend test-frontend  ## Run all tests

test-backend:  ## Run pytest
	cd backend && ../$(PY) -m pytest -q

test-frontend:  ## Type-check and build the frontend
	$(NPM) run build

# ----- lint -------------------------------------------------------------
lint: lint-backend lint-frontend  ## Lint both stacks

lint-backend:  ## Ruff check on backend
	cd backend && ../$(PY) -m ruff check app tests || true

lint-frontend:  ## ESLint on frontend (if configured)
	$(NPM) run lint --if-present

# ----- build ------------------------------------------------------------
build:  ## Production build of the frontend bundle
	$(NPM) run build

# ----- DB ---------------------------------------------------------------
migrate:  ## Apply outstanding alembic migrations
	cd backend && ../$(PY) -m alembic upgrade head

seed:  ## Run init_db() — seeds the default admin, settings, taxes, currencies
	cd backend && ../$(PY) -c "from app.db.init_db import init_db; init_db(); print('seeded')"

reindex:  ## Rebuild the SearchIndex from live tables
	cd backend && ../$(PY) -c "from app.services.search_index import rebuild_index; print(f'indexed: {rebuild_index()}')"

db-shell:  ## Open a sqlite3 shell against the dev DB
	sqlite3 backend/storage/enterprisecore.db

# ----- install ----------------------------------------------------------
install: install-backend install-frontend  ## Install all deps

install-backend:  ## Create venv + install backend deps
	cd backend && python -m venv .venv && ./.venv/Scripts/python.exe -m pip install --upgrade pip && ./.venv/Scripts/python.exe -m pip install -r requirements.txt

install-frontend:  ## Install frontend deps
	$(NPM) install

# ----- check ------------------------------------------------------------
check: lint test  ## Lint + test everything (CI gate)

# ----- clean ------------------------------------------------------------
clean:  ## Remove build artefacts (keeps the venv and the DB)
	rm -rf frontend/dist frontend/.vite-temp
	find backend -type d -name __pycache__ -exec rm -rf {} +
	find backend -type d -name .pytest_cache -exec rm -rf {} +
