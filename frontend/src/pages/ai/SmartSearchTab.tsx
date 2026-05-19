import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Search } from 'lucide-react';
import { api } from '../../lib/api';

type Result = {
  interpretation: string;
  answer: string;
  sources: { id: string; module: string; title: string; body: string }[];
};

export function SmartSearchTab() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const search = useMutation({
    mutationFn: async () => (await api.post<Result>('/ai/smart-search', { query })).data,
    onSuccess: setResult,
  });
  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <input className="ec-input flex-1" placeholder="Ask a question across your data… (e.g. 'Which invoices are overdue?')"
               value={query} onChange={(e) => setQuery(e.target.value)}
               onKeyDown={(e) => { if (e.key === 'Enter' && query.trim()) search.mutate(); }} />
        <button className="ec-btn-primary" disabled={!query.trim() || search.isPending} onClick={() => search.mutate()}>
          <Search size={16} /> {search.isPending ? '…' : 'Ask'}
        </button>
      </div>
      {result && (
        <div className="space-y-3">
          <div className="ec-card p-4">
            <p className="text-xs uppercase tracking-wider text-ink-muted">Interpretation</p>
            <p className="mt-1 text-sm">{result.interpretation}</p>
            <hr className="my-3 border-border" />
            <p className="text-xs uppercase tracking-wider text-ink-muted">Answer</p>
            <pre className="mt-1 whitespace-pre-wrap font-sans text-sm">{result.answer}</pre>
          </div>
          {result.sources.length > 0 && (
            <div className="ec-card p-4">
              <p className="mb-2 text-xs uppercase tracking-wider text-ink-muted">Sources ({result.sources.length})</p>
              <ul className="space-y-2">
                {result.sources.map((s, i) => (
                  <li key={s.id} className="rounded-md bg-surface-muted p-3 text-sm">
                    <p className="font-medium">[{i + 1}] {s.title}</p>
                    <p className="text-xs text-ink-muted">{s.module}</p>
                    <p className="mt-1 text-xs">{s.body}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
