# AI Knowledge Hub

A local-first, RAG-powered knowledge layer for EnterpriseCore AI Suite. Drop in
your PDFs, DOCX, Markdown or HTML files, then chat with them — answers stream
back token-by-token and cite the exact document chunks used.

Everything runs **offline** if you have Ollama installed. No data ever leaves
the machine unless you explicitly choose a paid provider (Anthropic / OpenAI).

---

## Where to find it

`/ai` → **Knowledge Hub** tabs:

| Tab | What it does |
| --- | --- |
| **Chat** | The existing freeform chat (now with an optional Stream toggle). |
| **RAG Chat** | Ask questions across one or more knowledge bases. Streams the answer with `[1] [2]` citation badges and a sources panel. |
| **Knowledge** | Create knowledge bases, upload/paste/fetch documents, monitor ingest, browse chunks. |
| **Models** | List installed Ollama models, pull new ones with live progress, see reachability. |

---

## Quick start (5 min)

1. **Install Ollama** ([ollama.com](https://ollama.com)) and run `ollama serve` if it isn't already running.
2. In the **Models** tab, pull both:
   - `llama3.1` (or any chat model)
   - `nomic-embed-text` (the default embedding model — 274 MB)
3. Go to **Knowledge** and click **+ New KB**. Pick "Ollama · nomic-embed-text".
4. Upload a PDF / DOCX / .md / .txt / .html file (or paste text, or paste a URL).
   Watch it walk through `queued → parsing → embedding → ready`.
5. Open **RAG Chat**, the new KB is auto-selected. Ask a question.
6. Watch the answer stream in with `[1] [2]` citations; hover a citation to highlight its source on the right.

---

## Knowledge bases

A KB is a named collection of documents that share an embedding model and
chunk settings. Cross-KB queries are allowed as long as both KBs use the same
embedding model.

**Settings** (when creating):
- **Embedding model** — `nomic-embed-text` (free, offline, 768d) by default. Also: `mxbai-embed-large`, `all-minilm`, OpenAI's `text-embedding-3-small`/`-large`.
- **Chunk size** (200–4000 chars, default 800) — bigger chunks keep more context together; smaller chunks make citations more precise.
- **Chunk overlap** (0–800 chars, default 100) — overlap prevents key facts at chunk boundaries from being lost.

You can edit a KB's name/description/chunk settings after creation. Changing the
embedding model after creation requires re-embedding all docs.

---

## Document ingest

Supported formats: **PDF, DOCX, MD/Markdown, TXT, HTML/HTM**. Up to 100 MB per file (configurable via `KNOWLEDGE_MAX_UPLOAD_MB`).

Three ways to add a document:
1. **Upload** — drag-drop one or more files.
2. **Paste** — paste raw text and give it a name.
3. **URL** — fetch a public web page.

After upload, the document goes through a background worker (polls every 5s — tunable via `KNOWLEDGE_INGEST_POLL_SECONDS`):
- **queued** → just landed, waiting for the worker.
- **parsing** → extracting text via `pypdf`, `python-docx` or `beautifulsoup4`.
- **embedding** → chunking and embedding via Ollama (or the configured provider).
- **ready** → all chunks have vectors, query-able.
- **failed** → an error occurred; see the message in the row.

The original blob and a cached extracted-text file are stored on disk under
`backend/storage/knowledge/<kb_id>/<doc_id>/`.

---

## RAG Chat

Streaming retrieval-augmented chat:
1. Embeds your question with the KB's embedding model.
2. Cosine-similarity ranks chunks across selected KBs.
3. Takes top-K (default 6), de-dupes by `(document, page)`.
4. Sends the system + sources + question to the chat model (Anthropic / OpenAI / Ollama).
5. Streams the answer back token-by-token.
6. Records a `KnowledgeQuery` audit row including the chunk IDs used.

**Controls:**
- KB chips (multi-select)
- Provider (Anthropic / OpenAI / Ollama — auto-falls-back to Ollama if no key)
- Top-K slider (1–15)
- Temperature slider (0.0–1.5, defaults to 0.3 for citations)
- `Ctrl/⌘+Enter` to send, `Esc` to abort the stream

**Citations** are rendered as clickable `[1] [2]` badges inline in the answer.
Hover or click one and the matching source card highlights on the right.

---

## Streaming chat (general)

The original Chat tab gained an optional **Stream** toggle in its header. With
it off (default), behavior is unchanged. With it on, responses stream
token-by-token using SSE. `Esc` cancels. Everything else (provider, model,
history, persistence, daily-spend cap) is identical.

---

## Ollama Model Manager

- **List** installed models with name, family, parameter size, disk size, last-modified.
- **Pull** new models — type a name (e.g. `qwen2.5:7b`) and watch the progress bar fill in real time.
- **Reachability badge** shows whether the configured `OLLAMA_HOST` responds.

If Ollama isn't reachable, the banner explains how to start it. The pseudo-hash
embedding fallback keeps the system working for development without Ollama, but
quality is bad — install Ollama for real use.

---

## API endpoints

All under `/api/v1/knowledge/` and require auth.

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/kb` | List KBs |
| `POST` | `/kb` | Create KB (manager+) |
| `GET` | `/kb/{id}` | KB detail (with counts) |
| `PATCH` | `/kb/{id}` | Update KB (manager+) |
| `DELETE` | `/kb/{id}` | Delete (manager+) |
| `GET` | `/kb/{id}/documents` | List docs |
| `POST` | `/kb/{id}/documents` | Multipart upload |
| `POST` | `/kb/{id}/documents/paste` | Paste text |
| `POST` | `/kb/{id}/documents/url` | Fetch URL |
| `GET` | `/kb/{id}/documents/{did}` | Doc detail |
| `GET` | `/kb/{id}/documents/{did}/chunks` | List chunks |
| `POST` | `/kb/{id}/documents/{did}/reindex` | Re-embed one doc |
| `POST` | `/kb/{id}/reindex` | Re-embed all docs in KB |
| `DELETE` | `/kb/{id}/documents/{did}` | Delete doc |
| `POST` | `/kb/{id}/query` | Retrieve only (no LLM) |
| `POST` | `/rag/chat` | RAG chat (SSE) |
| `GET` | `/queries` | Recent query audit |
| `GET` | `/models/ollama` | List Ollama models |
| `POST` | `/models/ollama/pull` | Pull a model (SSE) |

Plus `POST /api/v1/ai/chat/stream` (SSE variant of regular chat).

---

## Configuration

In `backend/.env`:

```
KNOWLEDGE_STORAGE_DIR=storage/knowledge
KNOWLEDGE_DEFAULT_EMBEDDING_PROVIDER=ollama
KNOWLEDGE_DEFAULT_EMBEDDING_MODEL=nomic-embed-text
KNOWLEDGE_INGEST_POLL_SECONDS=5
KNOWLEDGE_MAX_UPLOAD_MB=100
KNOWLEDGE_URL_FETCH_TIMEOUT=30
OLLAMA_HOST=http://127.0.0.1:11434
```

---

## Architecture notes

- **Vector store**: SQLite `LargeBinary` column holds each chunk's `float32` numpy array. Retrieval loads the relevant chunks into memory and does a single cosine top-K via matrix multiply. Fast up to ~50k chunks per query — well past realistic KB sizes for a personal/SMB install.
- **Chunker**: paragraph-aware sliding window with configurable overlap. Oversized blocks are sliced down to fit. Citations record `(page_number, char_start, char_end)` for precise pinning.
- **Worker**: APScheduler tick added to the existing housekeeping scheduler. Single-threaded (one doc at a time) to keep memory predictable.
- **Streaming**: every chat path (general + RAG) shares `app/services/ai.py::stream_call`, a generator of `(event_type, payload)` tuples that the FastAPI endpoint converts into SSE bytes. Provider fallback to Ollama works the same as for non-streaming calls.
- **No external services**: no FAISS, no Pinecone, no Chroma, no `sentence-transformers`. Just `numpy + sqlite + pypdf + python-docx`. Everything runs in the existing FastAPI process.

---

## Limitations / out of scope (for this build)

- No OCR — image-only PDFs come through empty. Add Tesseract later.
- No folder-watcher daemon (the `source_type='folder_watch'` enum value is reserved but unused).
- No cross-encoder re-rank. Just cosine similarity.
- No persistent in-memory cache; every query reloads chunks from SQLite. Fine until ~50k chunks per query.
- No citation overlays on the original PDF — citations point to char ranges and page numbers, not rendered highlights.

---

## Troubleshooting

**Status stuck on `embedding` forever.** Check `backend/storage/logs/`. Most common cause: Ollama isn't running and the hash fallback is being used for every chunk — slow on big docs but eventually finishes.

**"Selected KBs use different embedding models" warning in RAG Chat.** All
selected KBs must share the same embedding model for cross-KB retrieval to
make sense. Either pick KBs with matching models, or re-embed one of them.

**Citations missing or wrong.** Check the source panel — if the model is
ignoring `[1] [2]` instructions, lower the temperature (default 0.3) and/or
switch to a stronger model (e.g. `claude-sonnet-4-6` or `qwen2.5:14b`).

**PDF returns "Document has no extractable text"** — it's an image-only PDF.
Pre-OCR it with Tesseract or `ocrmypdf`, then re-upload.
