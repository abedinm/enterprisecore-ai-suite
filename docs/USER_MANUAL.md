# EnterpriseCore AI Suite — User Manual

> Replace every software subscription your company pays for — with one payment, your data never leaves your building, and it works even without internet.

## 1. Installing

### Option A — Desktop (.exe)

1. Download `EnterpriseCore-Setup-X.Y.Z.exe`.
2. Run it; choose an install location (defaults to `Program Files\EnterpriseCore`).
3. The bundled FastAPI backend starts automatically when you launch the app.

### Option B — Web (local server)

```powershell
git clone <repo>
cd EnterpriseCoreAI
npm run setup       # installs Python venv + frontend deps + electron deps
npm run dev         # starts backend (8765) + frontend (5173)
```

Open <http://127.0.0.1:5173>.

## 2. First-run setup

On first launch the system seeds a default admin user:

| Email | Password | Role |
|---|---|---|
| `admin@local` | `ChangeMe123!` | Admin |

**Sign in, open Settings → Account, and change this password immediately.**

## 3. Modules

| Group | Tools |
|---|---|
| **Finance** | Invoices (with PDF), Expenses, Payroll, Tax, Budgets, P&L, Balance Sheet, Cash Flow, Forecast, Currency, Multi-Currency, Recurring, Vendor Payments, Audit Trail, Dashboard |
| **HR** | Employees, Attendance, Leaves, Reviews, Recruitment, Onboarding, Org chart, Training, Discipline, Analytics |
| **CRM** | Leads, Pipeline (Kanban), Contacts, Follow-ups, Communications, Contracts, Proposals, Quotations, Campaigns, Segments, Analytics, AI Forecast |
| **Projects** | Projects, Tasks (Kanban), Sprints, Milestones, Gantt, Time tracking, Meetings, Minutes, Analytics |
| **Inventory** | Products, Stock movements, Suppliers, Warehouses, Purchase Orders, Shipments, Returns, Barcodes, Low-stock alerts, Analytics |
| **Documents** | Rich-text editor, Versioning, Templates, PDF export, E-signatures, Sharing, Tags, Bulk rename |
| **Communication** | Messaging, Announcements, Calendar, Notes, Polls, Feedback, Wiki |
| **Security** | Password vault, Backups, Login monitor, Compliance (GDPR/SOC2/etc.), Audit logs, Access control |
| **AI Coding** | Monaco editor, File explorer, Terminal, Git, AI chat, Code generation, Review, Bug fix, Snippets, API tester, DB query builder, Regex builder |
| **AI Brain** | Email/document writer, Meeting summariser, Financial narrator, HR insights, Sales forecast, Invoice analyser, Contract risk, Smart search, Sentiment, Usage dashboard, Chatbot builder |

## 4. AI configuration

EnterpriseCore can talk to:

- **Anthropic Claude** — set `ANTHROPIC_API_KEY` in `backend/.env`.
- **OpenAI** — set `OPENAI_API_KEY`.
- **Ollama (local, no key needed)** — run `ollama serve` on the same host. Configure `OLLAMA_HOST` if it isn't `http://127.0.0.1:11434`.

The app auto-falls back to Ollama if a paid provider fails. AI is fully optional — every business tool works without it.

## 5. Backups

1. Open **Security → Backups**.
2. Create a schedule with a name, cadence (daily/weekly), and target folder.
3. Run on demand with the *Run* button — produces a zipped `enterprisecore-YYYYMMDD-HHMMSS.zip` containing the SQLite DB and uploads.

To restore: stop the app, overwrite `backend/storage/enterprisecore.db` with the backup copy, restart.

## 6. Switching to PostgreSQL

Edit `backend/.env`:

```env
DB_BACKEND=postgres
POSTGRES_DSN=postgresql+psycopg2://user:pass@host:5432/enterprisecore
```

Then `npm run setup:backend` and restart. Tables are created automatically on first boot.

## 7. Keyboard shortcuts (AI Coding pane)

| Action | Keys |
|---|---|
| Save current file | `Ctrl+S` |
| Quick-find in editor | `Ctrl+F` |
| Command palette (Monaco) | `F1` |
| Submit AI chat | `Ctrl+Enter` |

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| Backend won't start | Check `backend/storage/logs/app.log`. Most common: port 8765 already in use. |
| Login says "invalid token type" | Clear browser local storage (`ec_access_token`, `ec_refresh_token`) and sign in again. |
| AI calls fail with 503 | The selected provider is down or unconfigured. The app will fall back to Ollama if running. |
| `cryptography` import error | Re-run `npm run setup:backend`. The Python venv may not be activated. |
| Migrations needed after upgrade | `alembic upgrade head` from the `backend/` directory. |

## 9. License

This is proprietary software. A license key activates production builds. Place your key in `backend/.env` as `LICENSE_KEY=…`. Without one, the app runs in development/evaluation mode (full features, no warranty).
