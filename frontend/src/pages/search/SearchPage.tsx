import { FormEvent, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Clock, Search } from 'lucide-react';
import { api, type FtsSearchResponse, type FtsSearchResult } from '../../lib/api';
import { groupByModule, moduleLabel, resultHref } from '../../lib/search';
import { cn, relativeTime } from '../../lib/utils';

type HistoryRow = { id: string; query: string; result_count: number; created_at: string };

// Filter chips. Each maps to a comma-separated list of entity_types the
// FTS5 endpoint accepts via the ``types`` query param.
const FILTERS: { value: string; label: string; types?: string }[] = [
  { value: '', label: 'Everywhere' },
  { value: 'finance', label: 'Finance', types: 'finance.customer,finance.vendor,finance.invoice,finance.expense' },
  { value: 'crm', label: 'CRM', types: 'crm.contact,crm.lead,crm.deal' },
  { value: 'hr', label: 'HR', types: 'hr.employee,hr.candidate,hr.job_opening' },
  { value: 'projects', label: 'Projects', types: 'projects.project,projects.task' },
  { value: 'documents', label: 'Documents', types: 'documents.document' },
  { value: 'communication', label: 'Communication', types: 'communication.announcement,communication.wiki_page' },
  { value: 'construction', label: 'Construction', types: 'construction.project,construction.risk' },
];

export function SearchPage() {
  const [query, setQuery] = useState('');
  const [filterValue, setFilterValue] = useState('');
  const [results, setResults] = useState<FtsSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState('');

  const history = useQuery({
    queryKey: ['search-history'],
    queryFn: async () => (await api.get<HistoryRow[]>('/search/history', { params: { limit: 10 } })).data,
  });

  async function runSearch(rawQuery: string, rawFilter: string) {
    const trimmed = rawQuery.trim();
    if (!trimmed) return;
    setLoading(true);
    setSubmitted(trimmed);
    try {
      const filter = FILTERS.find((f) => f.value === rawFilter);
      const params: Record<string, string | number> = { q: trimmed, limit: 50 };
      if (filter?.types) params.types = filter.types;
      const { data } = await api.get<FtsSearchResponse>('/search', { params });
      setResults(data.results);
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    runSearch(query, filterValue);
  }

  const grouped = groupByModule(results);

  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-brand-600">Global search</p>
        <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">Find anything</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-muted">
          Full-text search across every module — contacts, invoices, projects, tasks, documents,
          wiki pages, employees, and more. Results are ranked by relevance.
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
        <select
          className="ec-input max-w-[200px]"
          value={filterValue}
          onChange={(e) => setFilterValue(e.target.value)}
        >
          {FILTERS.map((f) => (
            <option key={f.value} value={f.value}>{f.label}</option>
          ))}
        </select>
        <button className="ec-btn-primary" type="submit" disabled={loading || !query.trim()}>
          <Search size={16} /> {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
        <div className="space-y-4">
          {submitted && !loading && results.length === 0 ? (
            <div className="ec-card p-6 text-sm text-ink-muted">No results for "{submitted}".</div>
          ) : null}
          {grouped.map((group) => (
            <section key={group.module} className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-muted">
                {moduleLabel(group.items[0].entity_type)}{' '}
                <span className="font-normal text-ink-subtle">({group.items.length})</span>
              </h2>
              <ul className="space-y-2">
                {group.items.map((r) => (
                  <li key={`${r.entity_type}-${r.entity_id}`} className="ec-card p-4">
                    <Link
                      to={resultHref(r)}
                      className="flex items-start justify-between gap-2 hover:underline"
                    >
                      <span className="font-medium">{r.title || '(untitled)'}</span>
                      <span className="ec-badge-blue uppercase tracking-wide text-[10px]">
                        {r.entity_type}
                      </span>
                    </Link>
                    {r.subtitle ? (
                      <p className="mt-0.5 text-xs text-ink-subtle">{r.subtitle}</p>
                    ) : null}
                    {r.body_excerpt ? (
                      <p className="mt-2 text-sm text-ink-muted">{r.body_excerpt}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
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
                      runSearch(row.query, filterValue);
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
