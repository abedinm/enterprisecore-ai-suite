import { FormEvent, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Clock, Search } from 'lucide-react';
import { api, type SearchHit, type SearchResponse } from '../../lib/api';
import { cn, relativeTime } from '../../lib/utils';

type HistoryRow = { id: string; query: string; result_count: number; created_at: string };

const MODULES = [
  { value: '', label: 'Everywhere' },
  { value: 'finance', label: 'Finance' },
  { value: 'crm', label: 'CRM' },
  { value: 'projects', label: 'Projects' },
  { value: 'documents', label: 'Documents' },
  { value: 'users', label: 'People' },
];

export function SearchPage() {
  const [query, setQuery] = useState('');
  const [module, setModule] = useState('');
  const [results, setResults] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState('');

  const history = useQuery({
    queryKey: ['search-history'],
    queryFn: async () => (await api.get<HistoryRow[]>('/search/history', { params: { limit: 10 } })).data,
  });

  async function runSearch(rawQuery: string, rawModule: string) {
    const trimmed = rawQuery.trim();
    if (!trimmed) return;
    setLoading(true);
    setSubmitted(trimmed);
    try {
      const { data } = await api.post<SearchResponse>('/search', {
        query: trimmed,
        module: rawModule || undefined,
        limit: 40,
      });
      setResults(data.items);
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    runSearch(query, module);
  }

  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-brand-600">Global search</p>
        <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">Find anything</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-muted">
          Searches invoices, customers, contacts, projects, tasks, documents, people, and the in-app search index.
        </p>
      </div>
      <form onSubmit={onSubmit} className="ec-card flex flex-wrap items-end gap-3 p-4">
        <div className="flex flex-1 items-center gap-2 rounded-lg border border-border bg-surface-muted px-3 py-1.5">
          <Search size={16} className="text-ink-muted" />
          <input
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-ink-subtle"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search anything across your business…"
            autoFocus
          />
        </div>
        <select className="ec-input max-w-[200px]" value={module} onChange={(e) => setModule(e.target.value)}>
          {MODULES.map((m) => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>
        <button className="ec-btn-primary" type="submit" disabled={loading || !query.trim()}>
          <Search size={16} /> {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
        <div className="space-y-3">
          {submitted && !loading && results.length === 0 ? (
            <div className="ec-card p-6 text-sm text-ink-muted">No results for "{submitted}".</div>
          ) : null}
          {results.map((r) => (
            <div key={`${r.module}-${r.id}`} className="ec-card p-4">
              <div className="flex items-start justify-between gap-2">
                <p className="font-medium">{r.title}</p>
                <span className="ec-badge-blue uppercase tracking-wide text-[10px]">{r.module}</span>
              </div>
              <p className="mt-0.5 text-xs text-ink-subtle">{r.entity_type}</p>
              {r.body && <p className="mt-2 text-sm text-ink-muted">{r.body}</p>}
            </div>
          ))}
        </div>
        <aside className="ec-card h-fit p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink-muted">
            <Clock size={14} /> Recent searches
          </div>
          {history.isLoading ? (
            <p className="text-sm text-ink-muted">Loading…</p>
          ) : history.data && history.data.length > 0 ? (
            <ul className="space-y-1">
              {history.data.map((row) => (
                <li key={row.id}>
                  <button
                    onClick={() => {
                      setQuery(row.query);
                      runSearch(row.query, module);
                    }}
                    className={cn(
                      'flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm transition hover:bg-surface-muted',
                    )}
                  >
                    <span className="truncate">{row.query}</span>
                    <span className="shrink-0 text-[11px] text-ink-subtle">{relativeTime(row.created_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ink-muted">No history yet.</p>
          )}
        </aside>
      </div>
    </div>
  );
}
