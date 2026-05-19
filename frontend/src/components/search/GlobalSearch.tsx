import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Search, X } from 'lucide-react';
import { api, type SearchHit, type SearchResponse } from '../../lib/api';
import { cn } from '../../lib/utils';

type GlobalSearchProps = {
  onSubmit?: () => void;
};

export function GlobalSearch({ onSubmit }: GlobalSearchProps) {
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<SearchHit[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
        event.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
      if (event.key === 'Escape') setOpen(false);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  useEffect(() => {
    if (!query.trim()) {
      setItems([]);
      return;
    }
    setLoading(true);
    const handle = setTimeout(async () => {
      try {
        const { data } = await api.post<SearchResponse>('/search', { query: query.trim(), limit: 8 });
        setItems(data.items);
        setActiveIndex(0);
      } catch {
        setItems([]);
      } finally {
        setLoading(false);
      }
    }, 220);
    return () => clearTimeout(handle);
  }, [query]);

  function navigateTo(hit: SearchHit) {
    setOpen(false);
    setQuery('');
    setItems([]);
    navigate(`/${hit.module}`);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, items.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const hit = items[activeIndex];
      if (hit) navigateTo(hit);
      else if (query.trim()) {
        onSubmit?.();
        setOpen(false);
      }
    }
  }

  return (
    <div ref={containerRef} className="relative max-w-xl">
      <div className="flex items-center gap-2 rounded-lg border border-border bg-surface-muted px-3 py-1.5 text-sm">
        <Search size={16} className="text-ink-muted" />
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder="Search invoices, people, tasks, documents... (Ctrl+K)"
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-ink-subtle"
        />
        {loading ? (
          <Loader2 size={14} className="animate-spin text-ink-muted" />
        ) : query ? (
          <button
            aria-label="Clear"
            onClick={() => {
              setQuery('');
              setItems([]);
              inputRef.current?.focus();
            }}
            className="rounded p-0.5 text-ink-muted hover:bg-surface-elevated"
          >
            <X size={14} />
          </button>
        ) : (
          <kbd className="hidden rounded border border-border bg-surface-elevated px-1.5 text-[10px] text-ink-subtle md:inline">
            Ctrl K
          </kbd>
        )}
      </div>

      {open && (query.trim() || loading) && (
        <div className="absolute left-0 right-0 z-40 mt-2 max-h-96 overflow-y-auto rounded-xl border border-border bg-surface-elevated p-1 shadow-lg">
          {loading && items.length === 0 ? (
            <p className="px-3 py-3 text-sm text-ink-muted">Searching…</p>
          ) : items.length === 0 ? (
            <p className="px-3 py-3 text-sm text-ink-muted">
              No results for "{query}".{' '}
              <button
                className="text-brand-600 hover:underline"
                onClick={() => {
                  onSubmit?.();
                  setOpen(false);
                }}
              >
                Open search page
              </button>
            </p>
          ) : (
            items.map((hit, idx) => (
              <button
                key={`${hit.module}-${hit.id}`}
                onClick={() => navigateTo(hit)}
                onMouseEnter={() => setActiveIndex(idx)}
                className={cn(
                  'flex w-full flex-col items-start gap-0.5 rounded-lg px-3 py-2 text-left text-sm transition',
                  idx === activeIndex ? 'bg-brand-600/10 text-ink' : 'hover:bg-surface-muted',
                )}
              >
                <div className="flex w-full items-center justify-between gap-2">
                  <span className="truncate font-medium">{hit.title}</span>
                  <span className="ec-badge-blue uppercase tracking-wide text-[10px]">{hit.module}</span>
                </div>
                {hit.body ? (
                  <span className="line-clamp-1 text-xs text-ink-muted">{hit.body}</span>
                ) : null}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
