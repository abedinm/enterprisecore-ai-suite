import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { BookOpen, Plus, Search } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';

type WikiPage = { id: string; title: string; body: string; parent_id: string | null; created_at: string; updated_at: string };

export function WikiTab() {
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const { data } = useQuery({
    queryKey: ['communication', 'wiki', q],
    queryFn: async () => (await api.get<WikiPage[]>('/communication/wiki', { params: q ? { q } : {} })).data,
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [show, setShow] = useState(false);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const save = useMutation({
    mutationFn: async () => (await api.post<WikiPage>('/communication/wiki', { title, body })).data,
    onSuccess: (p) => { setShow(false); setTitle(''); setBody(''); setSelected(p.id); qc.invalidateQueries({ queryKey: ['communication', 'wiki'] }); },
  });
  const page = data?.find((p) => p.id === selected);
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <BookOpen className="text-brand-600" size={20} />
        <input className="ec-input flex-1" placeholder="Search the wiki…" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="ec-btn-primary" onClick={() => setShow((v) => !v)}><Plus size={14} />{show ? 'Close' : 'New page'}</button>
      </div>
      {show && (
        <div className="rounded-xl border border-border bg-surface-muted p-4 space-y-3">
          <input className="ec-input" placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <textarea className="ec-input min-h-[200px] font-mono text-xs" placeholder="# Page body (markdown)…" value={body} onChange={(e) => setBody(e.target.value)} />
          <div className="flex justify-end">
            <button className="ec-btn-primary" disabled={!title || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save page'}</button>
          </div>
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-[260px_1fr]">
        <div className="ec-card overflow-hidden">
          <ul className="max-h-[60vh] overflow-y-auto">
            {data?.length ? data.map((p) => (
              <li key={p.id}>
                <button className={`block w-full px-3 py-2 text-left text-sm hover:bg-surface-muted ${selected === p.id ? 'bg-brand-600 text-white hover:bg-brand-700' : ''}`}
                        onClick={() => setSelected(p.id)}>
                  <p className="font-medium truncate">{p.title}</p>
                  <p className={`text-xs ${selected === p.id ? 'text-white/70' : 'text-ink-muted'}`}>{formatDateTime(p.updated_at)}</p>
                </button>
              </li>
            )) : <li className="p-4 text-center text-sm text-ink-muted">No pages.</li>}
          </ul>
        </div>
        <div className="ec-card p-5 min-h-[300px]">
          {page ? (
            <>
              <h2 className="text-xl font-semibold">{page.title}</h2>
              <pre className="mt-3 whitespace-pre-wrap font-sans text-sm">{page.body}</pre>
            </>
          ) : <p className="text-sm text-ink-muted">Select or create a page.</p>}
        </div>
      </div>
    </div>
  );
}
