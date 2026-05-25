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

This is proprietary software. A license key activates production builds. Place your key in `backend/.env` as `LICENSE_KEY=…`. Without one, the app runs in evaluation mode — the platform modules (finance, HR, CRM, projects, inventory, documents, communication, security, coding, AI brain, knowledge hub) plus webchat, marketing and the industry templates are fully available. The academic module pack stays gated until a license with `plan="edu"` is installed. See [SKU_FEATURES.md](SKU_FEATURES.md) for plan structure, feature matrix, and pilot guidance.

## 10. Web Chat Widget

The Web Chat module ships an embeddable multilingual chat widget that customers can drop onto any website. Conversations are logged inside EnterpriseCore and, once the visitor identifies themselves, linked to a CRM contact so the same record gathers email, calls, deals, and chat in one timeline.

### What it does

- Hosts one or more chat bots, each with its own system prompt, language preset, AI model, and rate-limit ceiling.
- Serves a single embeddable script at `https://<your-host>/widget.js` — drop one `<script>` tag onto any page and the chat bubble appears.
- Detects the visitor's language (English / Bangla / Hindi / Urdu) from the message text and replies in kind, or sticks to the preset language if you've pinned one.
- Resolves visitors to CRM contacts when the message contains an email or phone number, and writes every turn to the contact's CRM timeline so sales / support see chat history alongside email and call logs.

### Creating a bot

1. Open **Web Chat → Bots**. Click **New Bot**.
2. Give it a name (visible only to you), a description, and a system prompt — the persona / instructions the bot should follow.
3. Pick a language preset: `auto` lets the language detector route each message, or pin to `en` / `bn` / `hi` / `ur` for a single-language bot.
4. Pick the AI provider and model (defaults to Anthropic `claude-haiku-4-5`). The bot uses the server's configured provider key by default; supply a **BYO API key** if you want this bot to bill against a different account. BYO keys are Fernet-encrypted at rest and never returned in API responses — the bot list shows `has_byo_key: true/false` only.
5. Set the per-(bot, visitor) rate limit. Default is 20 messages per minute per visitor session.
6. Mark **Public** to allow the embeddable widget to address the bot. Private bots refuse `/chat/{id}` so the widget can never reach them.

### Embedding the widget

Open **Web Chat → Embed Snippet** for a bot. The page shows a ready-to-copy snippet:

```html
<script src="https://<your-host>/widget.js" data-bot-id="<bot-id>"></script>
```

Paste it before `</body>` on any page. The widget loads the bot's metadata (name, language) from `/api/v1/webchat/bots/public/<id>` and posts each message to `/api/v1/webchat/chat/<id>`. The widget script itself is unauthenticated and CORS-open; the chat endpoint enforces the bot's rate limit per visitor session and a 120/min global IP throttle so an abusive page can't drown the server.

### Conversations and CRM linking

**Web Chat → Conversations** lists every conversation across your bots, newest first. Each row links to the full transcript with token / cost metrics. When a visitor's first message includes an email or phone number, the service either finds the existing CRM `Contact` or creates a new one, attaches it to the conversation, and writes a `webchat` row to the contact's CRM `CommunicationEntry` timeline for each turn. From the CRM side, the contact's communications tab shows the chat alongside emails and call notes.

### Languages

The language detector uses Unicode script ranges (Latin, Bengali, Devanagari, Arabic) and picks the dominant script per message. Pure-punctuation / digits-only messages default to `en`. The bot's system prompt is in English; the language steering happens in the user-message wrap that the service adds before dispatching to the AI provider.

### Rate limits

Two limits stack on the public chat endpoint: a 120/min per-IP cap (set globally to absorb crawlers and probes) and a per-(bot, visitor-session) cap using the bot's configured `rate_limit_per_min`. Visitors who exceed the per-bot cap receive HTTP 429 with a `retry_after` seconds hint; visitors who exceed the IP cap receive the same status.

## 11. Marketing Site Builder

The Marketing module is a full website builder for the deployment's own marketing site. The admin Studio lives inside EnterpriseCore at **Marketing**; the rendered public site lives at `https://<your-host>/site/` and is meant to be the public-facing home page customers visit. It replaces a separate WordPress / Webflow / static-site subscription.

### Studio overview

The Studio is split into 13 sub-pages, accessible from the Marketing sidebar:

| Page | Purpose |
|---|---|
| **Dashboard** | Launch checklist + live preview link + recent activity |
| **Settings** | Site name, tagline, SEO title/description, contact info, base URL |
| **Navigation** | Header menu — label / route / enabled / order, atomically replaced on save |
| **Pages** | Home page section layout (hero, services, projects, testimonials, about, cta) |
| **Portfolio** | Project cards with image, summary, body, tags, featured flag, slug |
| **Blog** | Posts with draft / published status, publish date, author, category, tags, SEO |
| **Services** | Services list with icon, title, summary, details, price, featured flag |
| **Testimonials** | Quote + author + role |
| **FAQs** | Question + answer pairs |
| **Team** | Team member name + role + photo |
| **Social** | Social link platform + label + URL |
| **Media** | Image library — upload, browse, delete |
| **Templates** | Industry template gallery + apply action |

### Public site

The rendered site serves these routes off `/site/`:

- `/site/` — home page (hero + sections + featured projects + services + testimonials)
- `/site/about` — about page (sections + team + FAQs)
- `/site/services` — services list
- `/site/portfolio` and `/site/portfolio/<slug>` — project index and detail
- `/site/blog` and `/site/blog/<slug>` — post index and detail (drafts hidden)
- `/site/contact` — contact info from settings
- `/site/sitemap.xml` — XML sitemap of every public URL
- `/site/uploads/<id>` — media library image by id

Public pages are cached for 60 seconds at the edge (`Cache-Control: public, max-age=60`); refresh after an edit and you see the change. No auth is required for visitors; the only restriction is the plan gate — when the marketing feature is removed from the license the public site disappears entirely.

### Theme customization

Theme controls live under **Marketing → Settings**: primary color, accent color, heading font, body font, button style (square / rounded), density (comfortable / compact), and radius. These render as CSS custom properties in the public templates, so changes apply across every page without touching markup.

### Media library and EXIF

The Media page accepts PNG, JPEG, and WEBP up to 2 MB per file. The upload pipeline re-encodes every image server-side as PNG (which strips EXIF and ICC metadata, removing location data and camera fingerprints) and downscales to 1600px on the longest side so the library doesn't fill disk. Files live under `storage/uploads/marketing/<yyyy-mm>/<id>.png` and are served at `/site/uploads/<id>` with a one-day cache. Uploads carry a 5/min per-IP throttle.

## 12. Industry Templates

The Marketing module ships three starter templates that bootstrap an entire site (settings, theme, navigation, sections, services, portfolio, blog) in one click. Use them when standing up a new install for a customer or when piloting a vertical.

| Template | Designed for | Highlights |
|---|---|---|
| **Restaurant** | Neighborhood restaurants, cafes, bars | Menu-as-services, hours in contact info, terracotta and cream palette, rounded buttons, Fraunces headings |
| **Consultancy** | Strategy / engineering consultancies | Service ladder, case-study portfolio, structured testimonials, professional palette |
| **Professional services** | Lawyers, accountants, agencies | Service list, team-led about page, FAQ-heavy, conservative palette |

### Using a template

1. Open **Marketing → Templates**. Each tile shows the template name, description, and a preview.
2. Click **Use template**. A dialog asks whether to **wipe existing** content (default) or **append** to what's there:
   - **Wipe existing**: removes every current section, portfolio item, blog post, service, testimonial, FAQ, team member, social link, and the nav. Settings (name, tagline, theme) are overwritten with the template's. Use this when starting fresh.
   - **Append**: leaves existing content alone and adds the template's content on top. Settings are kept as-is. Use this when you want to layer a starter pack onto in-progress work.
3. The action requires Admin or Manager role — the suite refuses for Employee / Developer roles because wipe is destructive against the current site state.
4. A notification lands on your bell summarising what was applied and when.

### Customizing after applying

Once a template is applied, every entity it created is a regular row in the corresponding admin page — edit, reorder, or delete from **Marketing → Pages / Portfolio / Blog / Services / etc.** as normal. The Settings page lets you swap the palette, fonts, and SEO metadata. There is no link back to the template once applied; the rows are yours.

## 13. Academic Module Pack (EDU)

The Academic module pack is a separate SKU for schools, universities, and training providers. It does NOT ship enabled by default — the license must specify `plan="edu"` (or higher) for the module to appear in the nav and for academic endpoints to respond. See [SKU_FEATURES.md](SKU_FEATURES.md) for how to issue an EDU key.

### License requirement

```env
LICENSE_KEY=<your-edu-signed-key>     # plan="edu" inside the payload
```

Without an EDU license, the academic feature is gated off: `/api/v1/license/features` returns the active plan without `"academic"` in its features list, the frontend hides the Academic nav group, and any direct call to `/api/v1/academic/*` returns 403 from the plan gate before touching DB.

### New roles

EDU installs unlock four new roles on top of the platform's Admin / Manager / Developer / Employee:

| Role | What they can do |
|---|---|
| **Student** | View their own attendance, schedule, grades, submissions, finance records, advising notes; submit assignments and lab reports; browse the LMS library and study aids |
| **Teacher** | Mark attendance on their classes, post LMS resources, grade submissions, schedule exams, run advising sessions |
| **Registrar** | Maintain timetable slots, semesters, rooms, class enrollments; resolve scheduling conflicts |
| **Dean** | All registrar permissions plus institution-wide read across attendance, finance, advising |

Admin / Manager remain the highest tier and can perform any academic action. Role assignment happens in **Settings → Users** as usual.

### The 11 sub-modules

| Sub-module | Status |
|---|---|
| Attendance | Full — bulk-mark per class session, per-student summary, per-class report |
| Timetable | Full — slot CRUD with conflict detection, student/teacher/room schedule views |
| LMS Library | Functional CRUD — resources by course and type; teacher/admin write, all signed-in read |
| Lab Reports | Functional CRUD — students submit, teachers grade |
| Exam Scheduling | Functional CRUD — exam slots with room + invigilator |
| Academic Advising | Functional CRUD — advisor sessions with notes and action items |
| Group Projects | Functional CRUD — projects with member assignments |
| Study Aids | Functional CRUD — student-shared notes by course |
| Study Buddies | Functional CRUD — student study profile + match list |
| Student Finance | Functional CRUD — scholarships + per-student finance records |
| Deadlines | Functional CRUD — assignments with submission tracking |

"Functional CRUD" means the endpoints, schemas, models, migration, and a working React page exist; the deeper workflow features (auto-grading, conflict resolution UIs, advising templates) are scheduled deepenings. Attendance and Timetable are fully built end-to-end with conflict detection, per-role views, and complete test coverage.

### Sample usage flow

A teacher takes attendance for a Monday-morning session:

1. **Teacher** opens **Academic → Attendance**, picks their class, picks the session date, ticks each student present / absent / late / excused, and saves. The bulk-mark endpoint writes one `AcademicAttendanceRecord` per student in a single transaction.
2. **Student** opens **Academic → Attendance** to see their personal summary — count present / absent / late / excused across every class enrollment, plus a session-by-session list for any class they pick.
3. **Registrar** opens **Academic → Timetable**, creates a slot for the class on Tuesday 09:00-10:30 in Room 204. The slot service rejects the save if it would overlap with another slot in the same room or for the same class. The slot lands on every enrolled student's weekly schedule and on the teacher's weekly schedule automatically — both routes (`/timetable/students/me/schedule` and `/timetable/teachers/me/schedule`) compute the view from `AcademicTimetableSlot` joined to `AcademicClassEnrollment`.
4. **Student** opens **Academic → Timetable** to see their weekly schedule for the semester, grouped by day, with room number and teacher name.

A dean can spot-check institution-wide attendance through the class summary endpoint, which aggregates the per-session marks for any class in any semester.

The academic database tables are prefixed `academic_*` and live in the same SQLite / Postgres database as the rest of the suite, so backups, search, and audit cover them uniformly.
