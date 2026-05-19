import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, Copy, Loader2, Plus, Save, Send, Sparkles, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { cn } from '../../../lib/utils';
import { MonacoView } from '../EditorTabs';
import {
  deleteApiRequest, executeApiRequest, listApiRequests, saveApiRequest,
  updateApiRequest,
} from '../api';
import type { ApiExecResponse, ApiRequestSaved } from '../types';

type Props = { theme: 'vs-dark' | 'vs-light' };

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'];

type Draft = {
  id: string | null;
  name: string;
  method: string;
  url: string;
  headers: Record<string, string>;
  params: Record<string, string>;
  body: string;
  collection: string;
};

const BLANK: Draft = {
  id: null, name: 'Untitled request', method: 'GET', url: '', headers: {},
  params: {}, body: '', collection: '',
};

export function ApiTesterPanel({ theme }: Props) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Draft>(BLANK);
  const [response, setResponse] = useState<ApiExecResponse | null>(null);
  const [tab, setTab] = useState<'params' | 'headers' | 'body'>('params');
  const [responseTab, setResponseTab] = useState<'body' | 'headers'>('body');

  const saved = useQuery({ queryKey: ['api-requests'], queryFn: () => listApiRequests() });

  const exec = useMutation({
    mutationFn: () => executeApiRequest({
      method: draft.method, url: draft.url,
      headers: draft.headers, params: draft.params,
      body: draft.body || null,
    }),
    onSuccess: setResponse,
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Request failed'),
  });

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        name: draft.name, method: draft.method, url: draft.url,
        headers: draft.headers, params: draft.params,
        body: draft.body || null, collection: draft.collection || null,
      } as any;
      return draft.id ? updateApiRequest(draft.id, payload) : saveApiRequest(payload);
    },
    onSuccess: (r: ApiRequestSaved) => {
      toast.success('Saved');
      setDraft((d) => ({ ...d, id: r.id }));
      qc.invalidateQueries({ queryKey: ['api-requests'] });
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteApiRequest(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['api-requests'] }); toast.success('Deleted'); },
  });

  const grouped = useMemo(() => {
    const groups: Record<string, ApiRequestSaved[]> = {};
    (saved.data || []).forEach((r) => {
      const k = r.collection || 'Unfiled';
      groups[k] = groups[k] || [];
      groups[k].push(r);
    });
    return groups;
  }, [saved.data]);

  const load = (r: ApiRequestSaved) => {
    setDraft({
      id: r.id, name: r.name, method: r.method, url: r.url,
      headers: r.headers || {}, params: r.params || {},
      body: r.body || '', collection: r.collection || '',
    });
    setResponse(null);
  };

  const language = useMemo(() => {
    const ct = response?.content_type || '';
    if (ct.includes('json')) return 'json';
    if (ct.includes('xml')) return 'xml';
    if (ct.includes('html')) return 'html';
    return 'plaintext';
  }, [response]);

  const prettyBody = useMemo(() => {
    if (!response) return '';
    if (language === 'json') {
      try { return JSON.stringify(JSON.parse(response.body), null, 2); } catch { /* */ }
    }
    return response.body;
  }, [response, language]);

  return (
    <div className="grid h-full grid-cols-[200px_1fr] gap-2 p-2">
      <aside className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-border">
        <header className="flex shrink-0 items-center justify-between border-b border-border bg-surface-muted px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
          Saved
          <button title="New request" className="ec-btn-ghost p-0.5" onClick={() => setDraft(BLANK)}>
            <Plus size={11} />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-auto p-1">
          {Object.entries(grouped).map(([col, items]) => (
            <details key={col} open>
              <summary className="cursor-pointer rounded px-2 py-1 text-xs font-medium text-ink-muted hover:bg-surface-muted">{col}</summary>
              <ul className="pl-3">
                {items.map((r) => (
                  <li key={r.id} className={cn(
                    'group flex items-center gap-1 rounded px-1.5 py-1 text-[11px]',
                    draft.id === r.id ? 'bg-brand-600/15' : 'hover:bg-surface-muted',
                  )}>
                    <span className={cn('w-10 shrink-0 rounded px-1 text-[9px] font-bold', methodColor(r.method))}>{r.method}</span>
                    <button onClick={() => load(r)} className="flex-1 truncate text-left">{r.name}</button>
                    <button onClick={() => remove.mutate(r.id)} className="opacity-0 group-hover:opacity-100 text-rose-500">
                      <Trash2 size={10} />
                    </button>
                  </li>
                ))}
              </ul>
            </details>
          ))}
          {(saved.data || []).length === 0 && (
            <p className="p-3 text-[11px] text-ink-muted">No saved requests yet.</p>
          )}
        </div>
      </aside>

      <section className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-border">
        <div className="flex shrink-0 items-center gap-2 border-b border-border bg-surface-muted p-2">
          <input className="ec-input h-8 max-w-[180px] py-0 text-xs" placeholder="Request name"
                 value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          <input className="ec-input h-8 max-w-[120px] py-0 text-xs" placeholder="Collection"
                 value={draft.collection} onChange={(e) => setDraft({ ...draft, collection: e.target.value })} />
          <button className="ec-btn-secondary ml-auto text-xs" disabled={save.isPending} onClick={() => save.mutate()}>
            <Save size={11} /> Save
          </button>
        </div>

        <div className="flex shrink-0 items-center gap-2 border-b border-border bg-surface-elevated p-2">
          <select className={cn('h-8 rounded border border-border bg-surface-elevated px-2 text-xs font-bold', methodColor(draft.method))}
                  value={draft.method} onChange={(e) => setDraft({ ...draft, method: e.target.value })}>
            {METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <input className="ec-input h-8 flex-1 py-0 font-mono text-xs"
                 placeholder="https://api.example.com/endpoint"
                 value={draft.url}
                 onChange={(e) => setDraft({ ...draft, url: e.target.value })}
                 onKeyDown={(e) => { if (e.key === 'Enter' && draft.url && !exec.isPending) exec.mutate(); }} />
          <button className="ec-btn-primary text-xs" disabled={!draft.url || exec.isPending} onClick={() => exec.mutate()}>
            {exec.isPending ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
            Send
          </button>
        </div>

        <div className="flex shrink-0 border-b border-border bg-surface-muted">
          {(['params', 'headers', 'body'] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)}
                    className={cn('border-r border-border px-3 py-1.5 text-xs',
                                  tab === t ? 'bg-surface-elevated font-semibold text-brand-600' : 'text-ink-muted hover:bg-surface-elevated')}>
              {t}
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 overflow-auto">
          {tab === 'params' && (
            <KVEditor entries={draft.params} onChange={(p) => setDraft({ ...draft, params: p })} title="Query parameters" />
          )}
          {tab === 'headers' && (
            <KVEditor entries={draft.headers} onChange={(h) => setDraft({ ...draft, headers: h })} title="Headers" />
          )}
          {tab === 'body' && (
            <div className="h-full">
              <MonacoView value={draft.body} onChange={(v) => setDraft({ ...draft, body: v })} language="json" theme={theme} height="100%" />
            </div>
          )}
        </div>

        {response && (
          <div className="shrink-0 border-t border-border bg-surface-muted">
            <header className="flex items-center gap-3 px-3 py-1.5 text-[11px]">
              <span className={cn('rounded px-1.5 py-0.5 font-bold',
                response.status < 300 ? 'bg-emerald-500/20 text-emerald-300'
                : response.status < 400 ? 'bg-blue-500/20 text-blue-300'
                : 'bg-rose-500/20 text-rose-300')}>
                {response.status}
              </span>
              <span className="text-ink-muted">{response.duration_ms}ms • {(response.size_bytes / 1024).toFixed(1)} KB</span>
              {response.content_type && <span className="text-ink-subtle">{response.content_type.split(';')[0]}</span>}
              <button className="ml-auto ec-btn-ghost px-2 py-0.5 text-[11px]"
                      onClick={() => navigator.clipboard.writeText(prettyBody).then(() => toast.success('Copied'))}>
                <Copy size={11} /> Copy body
              </button>
            </header>
            <div className="flex border-t border-border">
              <button onClick={() => setResponseTab('body')} className={cn('border-r border-border px-3 py-1 text-xs',
                responseTab === 'body' ? 'bg-surface-elevated font-semibold' : 'text-ink-muted')}>Body</button>
              <button onClick={() => setResponseTab('headers')} className={cn('px-3 py-1 text-xs',
                responseTab === 'headers' ? 'bg-surface-elevated font-semibold' : 'text-ink-muted')}>Headers ({Object.keys(response.headers).length})</button>
            </div>
            <div style={{ height: 240 }}>
              {responseTab === 'body' ? (
                <MonacoView value={prettyBody} language={language} theme={theme} readOnly height="240px" />
              ) : (
                <pre className="h-full overflow-auto p-3 text-[11px]">
                  {Object.entries(response.headers).map(([k, v]) => (
                    <div key={k}><span className="text-brand-500">{k}</span>: {v}</div>
                  ))}
                </pre>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function methodColor(method: string): string {
  switch (method.toUpperCase()) {
    case 'GET': return 'bg-emerald-500/15 text-emerald-400';
    case 'POST': return 'bg-blue-500/15 text-blue-400';
    case 'PUT': return 'bg-amber-500/15 text-amber-400';
    case 'PATCH': return 'bg-violet-500/15 text-violet-400';
    case 'DELETE': return 'bg-rose-500/15 text-rose-400';
    default: return 'bg-surface-muted text-ink-muted';
  }
}

function KVEditor({
  entries, onChange, title,
}: { entries: Record<string, string>; onChange: (e: Record<string, string>) => void; title: string }) {
  const rows = Object.entries(entries);
  const add = () => onChange({ ...entries, '': '' });
  const update = (i: number, k: string, v: string) => {
    const newEntries: Record<string, string> = {};
    rows.forEach(([rk, rv], idx) => {
      if (idx === i) {
        if (k) newEntries[k] = v;
      } else {
        newEntries[rk] = rv;
      }
    });
    onChange(newEntries);
  };
  const remove = (k: string) => {
    const copy = { ...entries };
    delete copy[k];
    onChange(copy);
  };
  return (
    <div className="p-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">{title}</p>
        <button onClick={add} className="ec-btn-ghost px-2 py-0.5 text-[11px]"><Plus size={11} /> Add</button>
      </div>
      <table className="w-full text-xs">
        <thead><tr className="text-ink-muted"><th className="text-left">Key</th><th className="text-left">Value</th><th></th></tr></thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={3} className="py-3 text-[11px] text-ink-muted">No entries</td></tr>}
          {rows.map(([k, v], i) => (
            <tr key={i} className="border-t border-border">
              <td className="py-1 pr-2"><input className="ec-input h-7 py-0 text-xs" value={k}
                                                onChange={(e) => update(i, e.target.value, v)} /></td>
              <td className="py-1 pr-2"><input className="ec-input h-7 py-0 text-xs" value={v}
                                                onChange={(e) => update(i, k, e.target.value)} /></td>
              <td><button onClick={() => remove(k)} className="text-rose-500"><Trash2 size={11} /></button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
