# AI Knowledge Hub — Build Spec

**Scope of this build:** Add a local-first, RAG-powered Knowledge Hub to EnterpriseCore's AI Brain module. Combines two ideas:
- **#19** — Polished local-LLM chat (Ollama-first) with model management, streaming, prompt presets
- **#20** — RAG over your own documents (KBs, ingest, chunking, embeddings, citations)

**Mode of work:** Autonomous overnight build. Single-session. No user input required mid-build. Every commit must keep `npm run build` and `pytest backend/tests` green.

---

## 1. Success criteria (acceptance checklist)

The build is "done" when every item below is true. I check each one off as I go.

1. New tabs **"Knowledge"** and **"RAG Chat"** appear in `/ai` (AI Brain page) with the same visual style as existing tabs.
2. User can **create / rename / delete a Knowledge Base** with chosen embedding model + chunk settings.
3. User can **upload PDF, DOCX, TXT, MD, HTML** files to a KB via drag-drop; backend parses, chunks, embeds; status badge moves through `queued → parsing → embedding → ready`.
4. User can **paste raw text** or **submit a URL** to add a doc.
5. **Document detail panel** shows chunks with previews, page numbers, char ranges, and a "delete" + "re-embed" button per doc.
6. **RAG Chat**: pick one or more KBs, ask a question, response **streams** token-by-token, cites used chunks as **[1] [2] [3]**, sources panel on right lists them with preview + KB/doc name; clicking a citation badge scrolls/highlights the corresponding source.
7. **Ollama Model Manager** UI shows installed models, lets user pull a model by name (live progress), set the default chat model and default embedding model.
8. **Streaming chat** works for plain (non-RAG) chat too — the existing ChatTab gets an optional "Stream" toggle (off by default for backwards compat).
9. Works **fully offline** with Ollama running (no Anthropic/OpenAI key required for anything).
10. **Cost & usage** continue to be recorded (Ollama records `0`, paid providers record real `$`). Daily-spend cap still enforced.
11. **All existing AI features keep working unchanged** — ChatTab, WriterTab, SentimentTab, SmartSearchTab, MeetingTab, ChatbotsTab, UsageTab. No regressions.
12. **Backend tests** for the new module pass; new tests are added under `backend/tests/`.
13. **Frontend builds clean** (`cd frontend && npm run build`) and **typechecks** (`tsc -b`).
14. **Alembic migration** is generated and is forward-only (no destructive drops on existing tables).
15. Sidebar/nav unchanged except the existing **AI Brain** link now leads to a page that has the new tabs.
16. **Empty states, error toasts, keyboard shortcuts** (`Cmd/Ctrl+Enter` to send, `Esc` to cancel stream) all present.
17. **Dark mode** styled correctly (uses existing `bg-surface-*`, `text-ink-*` tokens).

---

## 2. Architecture

### High level
```
                ┌──────────────────────────────────────────────┐
                │              React frontend                   │
                │   AIBrainPage → KnowledgeTab / RagChatTab     │
                └────────────┬─────────────────────────────────┘
                             │ axios + EventSource (SSE)
                             ▼
                ┌──────────────────────────────────────────────┐
                │     FastAPI /api/v1/knowledge/*               │
                │     FastAPI /api/v1/ai/chat/stream            │
                └────┬──────────────┬────────────────┬─────────┘
                     │              │                │
            ┌────────▼───┐  ┌───────▼─────┐  ┌──────▼──────┐
            │ knowledge  │  │ ai service  │  │ APScheduler │
            │ service    │  │ (existing)  │  │ (ingest     │
            │ parse/     │  │ + new       │  │  worker)    │
            │ chunk/embed│  │ embed/stream│  └─────────────┘
            └────┬───────┘  └─────────────┘
                 │
                 ▼
            SQLite (or PG) — new tables: knowledge_bases, knowledge_documents,
            knowledge_chunks (+ embedding BLOB), knowledge_queries
                 │
                 ▼
            Storage: F:\EnterpriseCoreAI\backend\storage\knowledge\<kb_id>\<doc_id>\original.ext
```

### Vector store decision: **numpy + SQLite BLOB**
- No external service. No FAISS install pain on Windows.
- Each chunk stores its embedding as `bytes` (numpy `float32.tobytes()`) in a `BLOB` column.
- At query time: load all `(chunk_id, embedding)` rows for the target KB(s) into a numpy matrix (in-memory), compute cosine similarity in one batched dot-product, return top-K.
- Acceptable up to ~50k chunks per query (well above realistic KB sizes for the user's machine).
- Lazy improvement path noted but **not built** this session: persistent in-memory cache, on-disk HNSW.

### Embedding model strategy
- **Default**: Ollama `nomic-embed-text` (768-dim, free, offline). Endpoint: `POST {OLLAMA_HOST}/api/embeddings`.
- **Optional**: OpenAI `text-embedding-3-small` (1536-dim) if user supplies key.
- **Optional**: Anthropic does not currently expose an embeddings API — skip.
- **Last-resort fallback** (so the system never hard-fails in dev with no Ollama): deterministic hash-based 256-dim pseudo-embedding (terrible quality, just keeps the pipeline alive for unit tests). Logged loudly as `WARN`.
- All chunks within a KB **must use the same embedding model**. Switching the model on a KB triggers a full re-embed.

### Chunking strategy
- Default: **800-char windows, 100-char overlap**, respecting paragraph boundaries where possible.
- Configurable per KB: `chunk_size` (200–2000), `chunk_overlap` (0–400).
- For PDFs: chunks tagged with `page_number`. For DOCX/MD/TXT/HTML: `page_number = None`.
- `char_start`, `char_end` recorded on every chunk so the citation badge can pin-point the source.

### Streaming
- Anthropic: use the `client.messages.stream()` context manager.
- OpenAI: `stream=True` on `chat.completions.create`.
- Ollama: `stream=True` on `/api/chat` returns NDJSON; iterate `response.iter_lines()`.
- Backend exposes one endpoint, `POST /api/v1/ai/chat/stream`, that returns `text/event-stream`:
  - `event: token`, `data: {"text": "..."}`
  - `event: usage`, `data: {"tokens_in": n, "tokens_out": n, "cost_usd": "...", "provider": "...", "model": "...", "conversation_id": "..."}`
  - `event: error`, `data: {"detail": "..."}`
  - `event: done`, `data: {}`
- Frontend uses `EventSource` (works with FastAPI SSE; no extra lib).

### RAG flow
1. User asks question with `kb_ids: [id1, id2]` and `provider, model, top_k=6, temperature`.
2. Embed question with the **embedding model of the first KB** (assume all selected KBs share the same model — UI prevents mismatched selection).
3. Cosine-similarity rank across all chunks belonging to selected KBs.
4. Take top `K` chunks (configurable, default 6), de-duplicate by `(document_id, page_number)` to avoid same-page repeats.
5. Build prompt:
   ```
   You are a precise assistant. Answer using ONLY the sources below.
   Cite each claim with [#] matching the source number. If the sources are
   insufficient, say so plainly.

   SOURCES:
   [1] (KB: <kb-name> / Doc: <doc-name> / Page: <pg>) <chunk text>
   [2] ...

   QUESTION:
   <user question>
   ```
6. Stream answer; persist as a `KnowledgeQuery` row with `retrieved_chunk_ids` JSON for later auditing.
7. The frontend, in parallel, fetches the chunk metadata for the same IDs and renders the sources panel.

---

## 3. Backend — files to create / modify

### 3.1 New files

#### `backend/app/models/knowledge.py`
```python
"""SQLAlchemy models for the Knowledge Hub (RAG over local documents)."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, JSON, LargeBinary,
                        Numeric, String, Text)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, IdMixin, TimestampMixin


class KnowledgeBase(IdMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_bases"
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    embedding_provider: Mapped[str] = mapped_column(String(40), default="ollama", nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(120), default="nomic-embed-text", nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, default=768, nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, default=800, nullable=False)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class KnowledgeDocument(IdMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_documents"
    kb_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(400), index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)  # upload|paste|url
    source_ref: Mapped[str | None] = mapped_column(String(2000))  # original filename or URL
    storage_path: Mapped[str | None] = mapped_column(String(2000))  # absolute path to original blob
    mime_type: Mapped[str | None] = mapped_column(String(120))
    byte_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeChunk(IdMixin, Base):
    __tablename__ = "knowledge_chunks"
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True)
    kb_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    char_start: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)  # float32 .tobytes()
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KnowledgeQuery(IdMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_queries"
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    kb_ids_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded list[str]
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("ai_conversations.id", ondelete="SET NULL"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_chunk_ids_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list[str]
    answer: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(120))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0, nullable=False)
```

#### `backend/app/schemas/knowledge.py`
Pydantic schemas for every In/Out type — KB, Document, Chunk, IngestUploadIn, IngestPasteIn, IngestUrlIn, RagQueryIn, RagAnswerOut, OllamaModelOut, etc. (Mirror existing module patterns from `app/schemas/ai.py`.)

#### `backend/app/services/knowledge.py`
- `parse_document(path: str, mime: str) -> tuple[str, list[tuple[int|None, int, int, str]]]` — returns full text + list of (page_no, char_start, char_end, text) page blocks. Dispatches on mime/extension to `_parse_pdf`, `_parse_docx`, `_parse_html`, `_parse_md_or_txt`.
- `chunk_text(blocks, chunk_size, chunk_overlap) -> list[Chunk]` — sliding window with paragraph-aware boundaries.
- `embed_chunks(texts: list[str], provider, model) -> list[np.ndarray]` — batched Ollama / OpenAI call; falls back to hash-pseudo-embedding with a `WARN` log if both unavailable.
- `cosine_topk(query_vec, matrix, k) -> list[tuple[int, float]]` — numpy dot product on normalized vectors.
- `ingest_document(db, doc_id)` — full pipeline; updates `status` after each phase. Wraps everything in try/except and writes `error_message` on failure.
- `retrieve(db, kb_ids, query, top_k) -> list[KnowledgeChunk]` — embed query, scan chunks, return top-K.
- `build_rag_prompt(question, chunks) -> tuple[str, str]` — returns `(system, user)` strings.
- `list_ollama_models() -> list[dict]` — calls `GET {OLLAMA_HOST}/api/tags`.
- `pull_ollama_model(name) -> AsyncIterator[dict]` — streams `POST {OLLAMA_HOST}/api/pull`.

#### `backend/app/api/v1/endpoints/knowledge.py`
Endpoints (all under `/api/v1/knowledge`):
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/kb` | Create KB |
| `GET` | `/kb` | List KBs |
| `GET` | `/kb/{kb_id}` | Get KB detail (with doc count, chunk count, last ingest) |
| `PATCH` | `/kb/{kb_id}` | Update KB (name, desc, chunk params, embedding model — last one triggers reindex required flag) |
| `DELETE` | `/kb/{kb_id}` | Cascade-delete KB |
| `POST` | `/kb/{kb_id}/documents` | Upload file (multipart, `UploadFile`) — saves blob, creates row, enqueues ingest |
| `POST` | `/kb/{kb_id}/documents/paste` | Paste raw text (`{name, text}`) |
| `POST` | `/kb/{kb_id}/documents/url` | Fetch URL with `httpx`, store body, ingest |
| `GET` | `/kb/{kb_id}/documents` | List docs (with status) |
| `GET` | `/kb/{kb_id}/documents/{doc_id}` | Doc detail |
| `GET` | `/kb/{kb_id}/documents/{doc_id}/chunks` | List chunks |
| `DELETE` | `/kb/{kb_id}/documents/{doc_id}` | Delete doc + chunks + blob |
| `POST` | `/kb/{kb_id}/documents/{doc_id}/reindex` | Re-embed a single doc |
| `POST` | `/kb/{kb_id}/reindex` | Re-embed all docs in KB (used when embedding model changes) |
| `POST` | `/kb/{kb_id}/query` | Retrieval only (no LLM); returns top-K chunks |
| `POST` | `/rag/chat` | RAG chat (streaming SSE). Body: `{kb_ids, messages, provider, model, top_k, temperature, max_tokens, conversation_id?}` |
| `GET` | `/queries` | List recent RAG queries (audit) |
| `GET` | `/models/ollama` | List installed Ollama models |
| `POST` | `/models/ollama/pull` | Pull a model (streams progress as SSE) |

#### `backend/app/services/ingest_worker.py`
- An `APScheduler` job that polls `KnowledgeDocument.status == 'queued'` every 5 seconds and processes them serially.
- Hooked into existing `app/services/housekeeping.py` `start_scheduler()` flow.
- Concurrency: one at a time (avoids Ollama overload).

### 3.2 Modified files

#### `backend/app/services/ai.py`
Add these new top-level functions (do not change existing ones):
- `embed(texts: list[str], *, provider: str, model: str, api_key_override: str | None = None) -> list[np.ndarray]`
- `stream_anthropic(...)`, `stream_openai(...)`, `stream_ollama(...)` — async generators of `(event_type, payload)` tuples.
- `stream_call(...)` — unified streaming dispatch with fallback (mirror existing `call()`).

#### `backend/app/api/v1/endpoints/ai.py`
Add `POST /chat/stream` that wraps `stream_call`, persists user+assistant messages just like `/chat`, and yields SSE events. Reuses existing models.

#### `backend/app/api/v1/router.py`
Include the new `knowledge` router.

#### `backend/app/db/base.py` (verify) / `backend/app/db/init_db.py`
Ensure new models are imported so `Base.metadata.create_all` (or Alembic autogen) picks them up. (Inspect first — if init_db imports models explicitly, add the new module.)

#### `backend/app/models/__init__.py`
Export new models.

#### `backend/app/schemas/__init__.py`
Export new schemas.

#### `backend/requirements.txt`
Add (only what's not already there):
```
pypdf>=5.0
tiktoken>=0.8
```
(Already present: `python-docx`, `openpyxl`, `beautifulsoup4`, `markdown`, `numpy`, `httpx`, `ollama`, `anthropic`, `openai`.)

#### `backend/.env.example`
Add:
```
# Knowledge Hub
KNOWLEDGE_STORAGE_DIR=storage/knowledge
KNOWLEDGE_DEFAULT_EMBEDDING_PROVIDER=ollama
KNOWLEDGE_DEFAULT_EMBEDDING_MODEL=nomic-embed-text
KNOWLEDGE_INGEST_POLL_SECONDS=5
KNOWLEDGE_MAX_UPLOAD_MB=100
```

#### `backend/app/core/config.py`
Add corresponding `Settings` fields with defaults matching the env vars above.

### 3.3 Alembic migration
- Generate one revision file: `backend/alembic/versions/<rev>_add_knowledge_hub.py`.
- Up: create the four new tables with indexes.
- Down: drop them.
- Forward-only — no existing-table changes.

### 3.4 Tests (`backend/tests/`)
- `test_knowledge_parse.py` — parse a tiny PDF, DOCX, MD; assert correct char counts and page_count.
- `test_knowledge_chunk.py` — chunk known text; assert overlap, ordering, char_start/end.
- `test_knowledge_embed.py` — uses hash-fallback embeddings (no Ollama needed in CI); assert dim and normalization.
- `test_knowledge_retrieve.py` — seed three chunks, embed them, query, assert top-K order matches handwritten expectation.
- `test_knowledge_api.py` — happy-path: create KB, paste a doc, wait until ready (poll status with a 3s deadline using a synchronous ingest call rather than the scheduler), query, assert citations exist.
- `test_ai_stream.py` — mock the provider; assert SSE event sequence is `token+ → usage → done`.

Fixtures use `httpx.AsyncClient` against the FastAPI app — same pattern as any existing tests if present; otherwise build minimal `TestClient` fixtures.

---

## 4. Frontend — files to create / modify

### 4.1 New files

#### `frontend/src/lib/knowledge.ts`
Typed API client. Wraps `api` (axios) for all REST endpoints. Plus `streamRagChat(body, handlers)` and `streamModelPull(name, handlers)` using `EventSource` against the relative URL with `Authorization` header passed via a `?token=` query param (the existing `api` instance injects JWT — for SSE we need to pass it explicitly; backend endpoint accepts either header or query param).

#### `frontend/src/pages/ai/KnowledgeTab.tsx`
Three-column layout:
- **Left** (260px): KB list, "+ New KB" button at top, click to select. Right-click → rename / delete.
- **Middle** (flex): Document list of the selected KB. Header row with Upload / Paste / URL buttons + a status filter. Each row: name, source-type icon, status badge (color-coded), chunk count, ingested-at, kebab menu (re-embed / delete).
- **Right** (380px): Document detail when one is selected — meta, "Re-embed" button, scrollable chunk list with previews and a "show full text" toggle.
- "New KB" dialog: name, description, embedding provider + model dropdown (loads from `/knowledge/models/ollama` plus hardcoded OpenAI options), chunk_size + chunk_overlap sliders.
- "Upload" via drag-drop: shows a dropzone overlay while dragging anywhere over the middle column. Supports multi-file. Each file becomes a doc row that polls until `ready` or `failed`.

#### `frontend/src/pages/ai/RagChatTab.tsx`
Two-column layout:
- **Left** (flex): chat transcript + composer at bottom. Same overall structure as `ChatTab.tsx` for visual consistency, but with citation badges rendered inline.
- **Top toolbar**: KB multi-select (chips), Provider/Model selector, Top-K slider (default 6), Streaming toggle (on by default), Temperature slider.
- **Right** (340px): Sources panel. While streaming → shows skeleton; once `usage` event arrives → list of `[1] [2] [3]…` cards with KB name, doc name, page, snippet, and "open in Knowledge tab" link.
- Streaming UI uses `EventSource`, append each `token.text` to the in-flight assistant message div.
- `Esc` aborts the stream; `Cmd/Ctrl+Enter` sends.

#### `frontend/src/pages/ai/ModelManagerTab.tsx`
- Lists installed Ollama models (`/knowledge/models/ollama`).
- "Pull model" input → calls SSE pull endpoint, shows live progress bar.
- "Set as default chat model" / "Set as default embedding model" actions (writes to user prefs via existing settings endpoint, or stores in `localStorage` if no settings field — pick whichever is simpler at build time and document the choice in the file's top comment).

#### `frontend/src/components/knowledge/*`
Atomic components — `KbList`, `KbDialog`, `DocRow`, `DocStatusBadge`, `Dropzone`, `ChunkCard`, `CitationBadge`, `SourcesPanel`, `StreamingMessage`, `ModelPicker`, `PullProgressBar`.

### 4.2 Modified files

#### `frontend/src/pages/ai/AIBrainPage.tsx`
- Add `'knowledge' | 'rag' | 'models'` to `TabKey` union.
- Add three new tab buttons with `lucide-react` icons (`Database`, `BookOpen`, `Cpu`) — order: `chat, rag, knowledge, writer, sentiment, search, meeting, chatbots, models, usage`.
- Wire conditional render for the new tab components.

#### `frontend/src/pages/ai/ChatTab.tsx`
- Add a "Stream" toggle in the header (off by default).
- When on, route through new `streamChat` helper and render incrementally.
- **Do not change any existing behaviour when toggle is off.**

#### `frontend/src/lib/api.ts`
- Already exists. No structural changes — just ensure it exposes a way to read the current JWT so SSE endpoints can include it (most likely via `localStorage` since that's where `axios.defaults.headers` is set — verify at build).

#### `frontend/src/components/layout/AppShell.tsx`
- No nav changes required — AI Brain is already in the sidebar. (Visit the file at build time only if a sub-nav indicator is needed.)

### 4.3 Styling
- Use existing Tailwind tokens (`bg-surface`, `bg-surface-muted`, `bg-surface-elevated`, `text-ink`, `text-ink-muted`, `text-ink-subtle`, `border-border`, `bg-brand-600`, `ec-card`, `ec-btn-primary`, `ec-btn-ghost`, `ec-input`).
- Status badge colors: `queued`=zinc, `parsing`=amber, `embedding`=indigo, `ready`=emerald, `failed`=rose.

---

## 5. Storage layout

```
backend/storage/knowledge/
  <kb_id>/
    <doc_id>/
      original.<ext>         # original uploaded file
      extracted.txt          # cached parse output (for re-embed without re-parse)
```

`KNOWLEDGE_MAX_UPLOAD_MB` enforced at the upload endpoint.

---

## 6. Sequence diagrams (concise)

### Document ingest
```
client → POST /knowledge/kb/{kb}/documents (multipart)
api    → save blob to storage/knowledge/{kb}/{doc}/original.ext
       → create KnowledgeDocument(status='queued')
       → return 202 with doc row
scheduler tick (every 5s):
  find next 'queued' doc
  status = 'parsing'  → parse_document() → save extracted.txt → char/page counts
  status = 'embedding' → chunk_text() → embed_chunks() → insert KnowledgeChunk rows
  status = 'ready'    or 'failed' with error_message
client polls GET /knowledge/kb/{kb}/documents every 1s until status terminal
```

### RAG chat (SSE)
```
client → POST /knowledge/rag/chat {kb_ids, messages, top_k, ...}
api    → embed last user message
       → cosine_topk across selected KBs → chunks
       → build prompt
       → persist conversation/messages like /ai/chat
       → stream_call() → for each token: yield SSE 'token'
       → on finish: yield 'usage' with totals + conversation_id + chunk_ids
       → record AiUsageRecord + KnowledgeQuery
       → yield 'done'
client renders tokens live; on 'usage' fetches chunk previews to populate sources panel
```

---

## 7. Out of scope (explicitly NOT in this session)

- OCR for image-only PDFs (Tesseract integration).
- Cross-document semantic dedup / clustering.
- Multi-user KB sharing / permissions beyond owner.
- A vector index more sophisticated than full-scan numpy.
- Re-rank with a cross-encoder.
- Citations highlighted inside the original PDF preview.
- A folder-watcher daemon that auto-ingests new files in a folder. (`source_type='folder_watch'` is reserved in the schema but not wired up.)
- Web crawling beyond a single URL fetch.

These are noted so the schema accommodates them later but I don't burn time on them tonight.

---

## 8. Build order (milestones I check off as I go)

I create a TaskCreate list with these exact items. Each milestone leaves the app in a **buildable, runnable** state.

1. **M1 — DB layer + scaffolding** *(~45 min)*
   - Models, schemas, Alembic migration, router wiring, empty endpoints returning 501.
   - `init_db()` adjusted to register new models.
   - Verify migration applies on a fresh SQLite.
2. **M2 — KB CRUD + frontend skeleton** *(~45 min)*
   - Real KB CRUD endpoints + tests.
   - `KnowledgeTab.tsx` with left column (KB list + create) wired to React Query.
3. **M3 — Document ingest pipeline** *(~90 min)*
   - Parse (PDF/DOCX/MD/TXT/HTML), chunk, ingest worker via APScheduler.
   - Upload + paste + URL endpoints.
   - Middle column UI with status polling, drag-drop, dropzone.
4. **M4 — Embeddings + retrieval** *(~60 min)*
   - Ollama embed call + hash fallback + (optional) OpenAI.
   - cosine_topk; retrieve endpoint; reindex endpoint.
   - Document detail panel with chunk list.
5. **M5 — Streaming chat (general)** *(~60 min)*
   - SSE endpoint in `ai.py`; stream_call dispatch in `ai_svc`.
   - ChatTab "Stream" toggle wired.
   - Backend test with mocked provider.
6. **M6 — RAG chat with citations** *(~90 min)*
   - `/rag/chat` SSE endpoint.
   - `RagChatTab.tsx` with streaming + citations + sources panel.
   - `KnowledgeQuery` rows persisted.
7. **M7 — Model manager** *(~45 min)*
   - List + pull Ollama models (pull is SSE).
   - `ModelManagerTab.tsx` with progress bar.
8. **M8 — Polish + tests + memory update** *(~60 min)*
   - Empty states, keyboard shortcuts, error toasts, dark-mode pass.
   - Final test pass (backend `pytest`, frontend `npm run build`).
   - Update `MEMORY.md` with a note pointing to this build.
   - Write a short `docs/AI_KNOWLEDGE_HUB.md` user-facing README.

If I'm running ahead, I tackle bonus items in this order:
- (B1) `feature='kb_chat'` daily-spend ceiling preview shown in RagChatTab header.
- (B2) Per-KB "rebuild from extracted.txt" (skip parse step on reindex).
- (B3) Export a conversation as Markdown.

If I'm running behind, the cut order is reverse of bonus, then defer to "out of scope" anything in M7 except `list_ollama_models`.

---

## 9. Conventions I must follow

- File paths must match existing patterns: `app/api/v1/endpoints/`, `app/models/`, `app/schemas/`, `app/services/`, `frontend/src/pages/ai/`, `frontend/src/components/`.
- All money values use `Decimal` (`Numeric(12,6)` for cost_usd).
- All timestamps are UTC in DB.
- Currency: stay USD for cost.
- JWT-protected endpoints use `Depends(get_current_user)`.
- Admin/Manager-only actions use `Depends(require_roles(...))` — KB CRUD requires Manager+ for **create/delete**, any authenticated user can **read and query**.
- Logging via `loguru`.
- Errors via `AppError` (existing exception class) and `NotFoundError`.
- Style: Ruff config in `pyproject.toml` (line length 110, py311 target).
- React components: functional, hooks-based, react-query for server state, zustand only for cross-cutting state (auth/theme — don't add new global stores).
- No emojis in code or UI text.

---

## 10. The "Go" prompt

When the user is ready, they send any of:
- `go`
- `start`
- `build per docs/AI_KNOWLEDGE_HUB_SPEC.md`

…and I will:
1. Open this spec.
2. Create a TaskCreate list mirroring §8.
3. Execute milestones in order without further confirmation.
4. Commit nothing to git (the user said no destructive actions; commits will be staged for review when they wake up unless they tell me otherwise — actually since the repo isn't a git repo per session env, I just leave files on disk).
5. Stop and report at the end of M8 (or sooner if blocked).
6. Update `MEMORY.md` with a fresh `[[knowledge-hub-build]]` entry summarizing what landed.

I won't ask follow-up questions during the build unless I hit something this spec doesn't cover — and even then I'll pick the simpler-of-two and note it inline in code with a `# DECISION:` comment for review.
