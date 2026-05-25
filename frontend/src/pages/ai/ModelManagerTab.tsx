import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import {
  AlertCircle, CheckCircle2, Cpu, Download, RefreshCw, Server, Wifi, WifiOff,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { API_BASE, tokenStore } from '../../lib/api';
import { formatBytes, knowledgeApi } from '../../lib/knowledge';
import { formatDateTime, relativeTime } from '../../lib/utils';

type PullState = {
  status: string;
  detail?: string;
  completed: number;
  total: number;
  finished: boolean;
  error?: string;
};

const RECOMMENDED = [
  { name: 'llama3.1', size: '8B params · 4.7 GB · general chat', purpose: 'chat' },
  { name: 'llama3.2', size: '3B params · 2.0 GB · faster chat', purpose: 'chat' },
  { name: 'qwen2.5:7b', size: '7B params · 4.4 GB · strong reasoning', purpose: 'chat' },
  { name: 'mistral', size: '7B params · 4.1 GB · concise responses', purpose: 'chat' },
  { name: 'nomic-embed-text', size: '137M params · 274 MB · text embeddings (768d)', purpose: 'embed' },
  { name: 'mxbai-embed-large', size: '335M params · 670 MB · larger embeddings (1024d)', purpose: 'embed' },
];

export function ModelManagerTab() {
  const qc = useQueryClient();
  const modelsQuery = useQuery({
    queryKey: ['knowledge', 'ollama-models'],
    queryFn: knowledgeApi.listOllamaModels,
    refetchInterval: 30_000,
  });

  const [pullName, setPullName] = useState('');
  const [pull, setPull] = useState<PullState | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  // Ollama's /api/pull emits its own `progress` SSE event with byte-level
  // counters, which streamSse's helper doesn't surface — so we drive the
  // fetch directly here.
  async function startPullDirect(name: string) {
    const target = name.trim();
    if (!target) {
      toast.error('Enter a model name');
      return;
    }
    if (pull && !pull.finished) {
      toast.error('A pull is already in progress');
      return;
    }
    setPullName(target);
    setPull({ status: 'starting', completed: 0, total: 0, finished: false });
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const token = tokenStore.getAccess();
      const r = await fetch(`${API_BASE}/knowledge/models/ollama/pull`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ name: target }),
        signal: controller.signal,
      });
      if (!r.ok || !r.body) {
        const detail = await r.text().catch(() => `HTTP ${r.status}`);
        setPull({ status: 'failed', completed: 0, total: 0, finished: true, error: detail });
        toast.error(detail);
        return;
      }
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      let event = 'message';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, idx);
          buf = buf.slice(idx + 1);
          if (line.startsWith('event:')) event = line.slice(6).trim();
          else if (line.startsWith('data:')) {
            const raw = line.slice(5).trim();
            if (!raw) continue;
            let parsed: any;
            try { parsed = JSON.parse(raw); } catch { parsed = { _raw: raw }; }
            if (event === 'progress') {
              setPull((p) =>
                p && {
                  ...p,
                  status: parsed.status || p.status,
                  completed: parsed.completed ?? p.completed,
                  total: parsed.total ?? p.total,
                  detail: parsed.digest || parsed.status,
                },
              );
            } else if (event === 'error') {
              setPull((p) => p && { ...p, finished: true, error: parsed.detail });
              toast.error(parsed.detail || 'Pull failed');
            } else if (event === 'done') {
              setPull((p) => p && { ...p, finished: true, status: 'done' });
              toast.success(`Pulled ${target}`);
              qc.invalidateQueries({ queryKey: ['knowledge', 'ollama-models'] });
            }
            event = 'message';
          }
        }
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        setPull((p) => p && { ...p, finished: true, error: e?.message });
        toast.error(e?.message || 'Pull failed');
      }
    } finally {
      abortRef.current = null;
    }
  }

  function cancelPull() {
    abortRef.current?.abort();
    abortRef.current = null;
    setPull((p) => p && { ...p, finished: true, error: 'cancelled' });
  }

  const data = modelsQuery.data;
  const reachable = data?.reachable;

  return (
    <div className="space-y-4">
      <header className="ec-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300">
              <Cpu size={18} />
            </div>
            <div>
              <h3 className="text-base font-semibold">Ollama models</h3>
              <p className="mt-0.5 text-xs text-ink-muted">
                Manage local LLMs used by Chat, RAG Chat, and embeddings.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <ReachabilityBadge host={data?.host} reachable={reachable} />
            <button
              onClick={() => modelsQuery.refetch()}
              className="ec-btn-secondary !py-1.5 text-xs"
              disabled={modelsQuery.isFetching}
              title="Refresh"
            >
              <RefreshCw size={12} className={modelsQuery.isFetching ? 'animate-spin' : ''} />
              Refresh
            </button>
          </div>
        </div>
      </header>

      <section className="ec-card p-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex-1">
            <label className="ec-label">Pull a new model</label>
            <div className="flex gap-2">
              <input
                value={pullName}
                onChange={(e) => setPullName(e.target.value)}
                placeholder="e.g. llama3.1 or nomic-embed-text"
                className="ec-input"
              />
              {pull && !pull.finished ? (
                <button className="ec-btn-danger" onClick={cancelPull}>
                  Cancel
                </button>
              ) : (
                <button
                  className="ec-btn-primary"
                  onClick={() => startPullDirect(pullName)}
                  disabled={!pullName.trim() || reachable === false}
                >
                  <Download size={14} /> Pull
                </button>
              )}
            </div>
          </div>
        </div>

        {pull && (
          <div className="mt-3 rounded-lg border border-border bg-surface-muted p-3 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-medium">{pullName}</span>
              <span className="text-ink-muted">
                {pull.finished
                  ? pull.error
                    ? <span className="text-rose-600">{pull.error}</span>
                    : <span className="text-emerald-600 inline-flex items-center gap-1"><CheckCircle2 size={11} /> Done</span>
                  : pull.status}
              </span>
            </div>
            {pull.total > 0 && (
              <>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-elevated">
                  <div
                    className="h-full bg-brand-600 transition-all"
                    style={{ width: `${Math.min(100, (pull.completed / pull.total) * 100)}%` }}
                  />
                </div>
                <p className="mt-1 text-[11px] text-ink-subtle">
                  {formatBytes(pull.completed)} / {formatBytes(pull.total)}
                </p>
              </>
            )}
          </div>
        )}

        <div className="mt-4">
          <p className="ec-label">Recommended</p>
          <div className="flex flex-wrap gap-2">
            {RECOMMENDED.map((r) => (
              <button
                key={r.name}
                className="rounded-lg border border-border bg-surface-elevated px-3 py-2 text-left text-xs hover:border-brand-500"
                onClick={() => setPullName(r.name)}
                title={`${r.name} — ${r.purpose}`}
              >
                <p className="font-medium">{r.name}</p>
                <p className="text-[10px] text-ink-muted">{r.size}</p>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="ec-card overflow-hidden">
        <div className="flex items-center justify-between border-b border-border bg-surface-muted px-4 py-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">
            Installed
          </p>
          <span className="text-xs text-ink-muted">
            {data?.models?.length ?? 0} model{(data?.models?.length ?? 0) === 1 ? '' : 's'}
          </span>
        </div>
        {!reachable && (
          <div className="flex items-center gap-2 border-b border-border bg-amber-50 px-4 py-3 text-xs text-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
            <AlertCircle size={14} />
            Ollama is not reachable at <code className="rounded bg-amber-100 px-1 dark:bg-amber-900/40">{data?.host}</code>.
            Start it with <code className="rounded bg-amber-100 px-1 dark:bg-amber-900/40">ollama serve</code> or set
            <code className="rounded bg-amber-100 px-1 dark:bg-amber-900/40">OLLAMA_HOST</code> in the backend env.
          </div>
        )}
        {reachable && (data?.models?.length ?? 0) === 0 && (
          <div className="grid place-items-center px-4 py-8 text-center">
            <Server size={20} className="mx-auto mb-2 text-ink-subtle" />
            <p className="text-sm font-medium">No local models yet</p>
            <p className="mt-1 text-xs text-ink-muted">
              Pull one above — <code>llama3.1</code> is a solid starting point.
            </p>
          </div>
        )}
        {(data?.models?.length ?? 0) > 0 && (
          <table className="ec-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Family</th>
                <th>Parameters</th>
                <th className="text-right">Size</th>
                <th>Modified</th>
              </tr>
            </thead>
            <tbody>
              {data!.models.map((m) => (
                <tr key={m.name} className="hover:bg-surface-muted/50">
                  <td>
                    <span className="font-mono text-xs">{m.name}</span>
                  </td>
                  <td className="text-xs text-ink-muted">{m.family ?? '—'}</td>
                  <td className="text-xs text-ink-muted">{m.parameter_size ?? '—'}</td>
                  <td className="text-right text-xs tabular-nums">{formatBytes(m.size_bytes)}</td>
                  <td className="text-xs text-ink-muted" title={formatDateTime(m.modified_at)}>
                    {relativeTime(m.modified_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function ReachabilityBadge({ host, reachable }: { host?: string; reachable?: boolean }) {
  if (reachable === undefined) {
    return (
      <span className="ec-badge bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200">
        Checking…
      </span>
    );
  }
  return reachable ? (
    <span className="ec-badge-green" title={host}>
      <Wifi size={11} /> <span className="ml-1">Connected</span>
    </span>
  ) : (
    <span className="ec-badge-rose" title={host}>
      <WifiOff size={11} /> <span className="ml-1">Offline</span>
    </span>
  );
}
