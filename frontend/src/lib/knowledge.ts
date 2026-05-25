import { api, API_BASE, tokenStore } from './api';

export type KbOut = {
  id: string;
  owner_id: string | null;
  name: string;
  description: string | null;
  embedding_provider: string;
  embedding_model: string;
  embedding_dim: number;
  chunk_size: number;
  chunk_overlap: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  document_count: number;
  chunk_count: number;
  ready_count: number;
};

export type KbCreateIn = {
  name: string;
  description?: string | null;
  embedding_provider?: string;
  embedding_model?: string;
  embedding_dim?: number;
  chunk_size?: number;
  chunk_overlap?: number;
};

export type KbUpdateIn = Partial<KbCreateIn> & { is_active?: boolean };

export type DocStatus = 'queued' | 'parsing' | 'embedding' | 'ready' | 'failed';

export type DocOut = {
  id: string;
  kb_id: string;
  name: string;
  source_type: 'upload' | 'paste' | 'url' | string;
  source_ref: string | null;
  mime_type: string | null;
  byte_size: number;
  status: DocStatus | string;
  error_message: string | null;
  page_count: number;
  char_count: number;
  chunk_count: number;
  ingested_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ChunkOut = {
  id: string;
  document_id: string;
  kb_id: string;
  ordinal: number;
  text: string;
  page_number: number | null;
  char_start: number;
  char_end: number;
  token_count: number;
  embedding_model: string | null;
  has_embedding: boolean;
  created_at: string;
};

export type RetrievedChunk = {
  chunk_id: string;
  document_id: string;
  document_name: string;
  kb_id: string;
  kb_name: string;
  text: string;
  page_number: number | null;
  score: number;
};

export type RetrieveOut = {
  query: string;
  chunks: RetrievedChunk[];
  embedding_provider: string;
  embedding_model: string;
  latency_ms: number;
};

export type OllamaModel = {
  name: string;
  size_bytes: number;
  modified_at: string | null;
  parameter_size: string | null;
  family: string | null;
};

export type OllamaModelsOut = {
  models: OllamaModel[];
  host: string;
  reachable: boolean;
};

// ---- REST wrappers --------------------------------------------------------
export const knowledgeApi = {
  listKbs: () => api.get<KbOut[]>('/knowledge/kb').then((r) => r.data),
  createKb: (body: KbCreateIn) => api.post<KbOut>('/knowledge/kb', body).then((r) => r.data),
  getKb: (id: string) => api.get<KbOut>(`/knowledge/kb/${id}`).then((r) => r.data),
  updateKb: (id: string, body: KbUpdateIn) =>
    api.patch<KbOut>(`/knowledge/kb/${id}`, body).then((r) => r.data),
  deleteKb: (id: string) => api.delete(`/knowledge/kb/${id}`).then(() => true),

  listDocs: (kbId: string) =>
    api.get<DocOut[]>(`/knowledge/kb/${kbId}/documents`).then((r) => r.data),
  getDoc: (kbId: string, docId: string) =>
    api.get<DocOut>(`/knowledge/kb/${kbId}/documents/${docId}`).then((r) => r.data),
  uploadDoc: (kbId: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return api
      .post<DocOut>(`/knowledge/kb/${kbId}/documents`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data);
  },
  pasteDoc: (kbId: string, name: string, text: string) =>
    api
      .post<DocOut>(`/knowledge/kb/${kbId}/documents/paste`, { name, text })
      .then((r) => r.data),
  urlDoc: (kbId: string, url: string, name?: string) =>
    api
      .post<DocOut>(`/knowledge/kb/${kbId}/documents/url`, { url, name })
      .then((r) => r.data),
  deleteDoc: (kbId: string, docId: string) =>
    api.delete(`/knowledge/kb/${kbId}/documents/${docId}`).then(() => true),
  reindexDoc: (kbId: string, docId: string) =>
    api
      .post<DocOut>(`/knowledge/kb/${kbId}/documents/${docId}/reindex`)
      .then((r) => r.data),
  reindexKb: (kbId: string) =>
    api.post(`/knowledge/kb/${kbId}/reindex`).then((r) => r.data),

  listChunks: (kbId: string, docId: string) =>
    api
      .get<ChunkOut[]>(`/knowledge/kb/${kbId}/documents/${docId}/chunks`)
      .then((r) => r.data),

  retrieve: (kbId: string, query: string, topK = 6) =>
    api
      .post<RetrieveOut>(`/knowledge/kb/${kbId}/query`, { query, top_k: topK })
      .then((r) => r.data),

  listOllamaModels: () =>
    api.get<OllamaModelsOut>('/knowledge/models/ollama').then((r) => r.data),
};

// ---- SSE streaming helpers ------------------------------------------------
export type SseEventHandler = (event: string, data: any) => void;

/** Stream a POST request using fetch + ReadableStream so we can attach
 * the Authorization header (EventSource won't let us).
 */
export async function streamSse(
  path: string,
  body: any,
  handlers: {
    onToken?: (text: string) => void;
    onUsage?: (data: any) => void;
    onSources?: (data: any) => void;
    onError?: (detail: string) => void;
    onDone?: (data: any) => void;
    signal?: AbortSignal;
  },
): Promise<void> {
  const token = tokenStore.getAccess();
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal: handlers.signal,
  });
  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => `HTTP ${res.status}`);
    handlers.onError?.(detail);
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = 'message';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 1);
      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        const raw = line.slice(5).trim();
        if (!raw) continue;
        let parsed: any;
        try {
          parsed = JSON.parse(raw);
        } catch {
          parsed = { _raw: raw };
        }
        if (currentEvent === 'token') handlers.onToken?.(parsed.text ?? '');
        else if (currentEvent === 'usage') handlers.onUsage?.(parsed);
        else if (currentEvent === 'sources') handlers.onSources?.(parsed);
        else if (currentEvent === 'error') handlers.onError?.(parsed.detail ?? 'Unknown error');
        else if (currentEvent === 'done') handlers.onDone?.(parsed);
        currentEvent = 'message';
      }
    }
  }
}

export type DocStatusStyle = { badge: string; label: string };

export function docStatusStyle(status: string): DocStatusStyle {
  switch (status) {
    case 'queued':
      return { badge: 'ec-badge bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200', label: 'Queued' };
    case 'parsing':
      return { badge: 'ec-badge-amber', label: 'Parsing' };
    case 'embedding':
      return { badge: 'ec-badge bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300', label: 'Embedding' };
    case 'ready':
      return { badge: 'ec-badge-green', label: 'Ready' };
    case 'failed':
      return { badge: 'ec-badge-rose', label: 'Failed' };
    default:
      return { badge: 'ec-badge bg-zinc-200 text-zinc-700', label: status };
  }
}

export function formatBytes(bytes: number): string {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let v = bytes;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}
