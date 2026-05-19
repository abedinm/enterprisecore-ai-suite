import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Plus, Save, Trash2, Eye, EyeOff } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';
import type { Document } from './types';

const VISIBILITIES = ['private', 'team', 'public'];

export function EditorTab() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [visibility, setVisibility] = useState('private');
  const [dirty, setDirty] = useState(false);
  const [preview, setPreview] = useState(false);

  const docs = useQuery({
    queryKey: ['docs', search],
    queryFn: async () => (await api.get<Document[]>('/documents', { params: search ? { q: search } : {} })).data,
  });

  useEffect(() => {
    if (docs.data?.length && !selectedId) {
      setSelectedId(docs.data[0].id);
    }
  }, [docs.data, selectedId]);

  const current = docs.data?.find((d) => d.id === selectedId);
  useEffect(() => {
    if (current && !dirty) {
      setTitle(current.title);
      setContent(current.content);
      setVisibility(current.visibility);
    }
  }, [current, dirty]);

  const save = useMutation({
    mutationFn: async () => {
      const body = { title, content, visibility, file_path: null };
      if (selectedId) return (await api.patch<Document>(`/documents/${selectedId}`, body)).data;
      return (await api.post<Document>('/documents', body)).data;
    },
    onSuccess: (d) => { setDirty(false); setSelectedId(d.id); qc.invalidateQueries({ queryKey: ['docs'] }); },
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/documents/${id}`)).data,
    onSuccess: () => { setSelectedId(null); setDirty(false); setTitle(''); setContent(''); qc.invalidateQueries({ queryKey: ['docs'] }); },
  });

  function newDoc() {
    setSelectedId(null); setTitle('Untitled'); setContent(''); setVisibility('private'); setDirty(true);
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
      <div className="ec-card p-3 space-y-2">
        <div className="flex gap-2">
          <input className="ec-input !py-1" placeholder="Search…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <button className="ec-btn-primary !py-1 !px-2" title="New" onClick={newDoc}><Plus size={14} /></button>
        </div>
        <ul className="max-h-[60vh] overflow-y-auto space-y-1">
          {docs.data?.length ? docs.data.map((d) => (
            <li key={d.id}>
              <button onClick={() => { setSelectedId(d.id); setDirty(false); }}
                className={`block w-full rounded-md px-3 py-2 text-left text-sm ${selectedId === d.id ? 'bg-brand-600 text-white' : 'hover:bg-surface-muted'}`}>
                <p className="truncate font-medium">{d.title}</p>
                <p className={`text-xs ${selectedId === d.id ? 'text-white/70' : 'text-ink-muted'}`}>{formatDateTime(d.updated_at)}</p>
              </button>
            </li>
          )) : <li className="px-3 py-6 text-center text-sm text-ink-muted">No documents.</li>}
        </ul>
      </div>

      <div className="ec-card p-5 space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="grow"><label className="ec-label">Title</label><input className="ec-input" value={title} onChange={(e) => { setTitle(e.target.value); setDirty(true); }} /></div>
          <div><label className="ec-label">Visibility</label>
            <select className="ec-input" value={visibility} onChange={(e) => { setVisibility(e.target.value); setDirty(true); }}>
              {VISIBILITIES.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <button className="ec-btn-secondary" onClick={() => setPreview((p) => !p)}>
            {preview ? <><EyeOff size={14} />Edit</> : <><Eye size={14} />Preview</>}
          </button>
          <button className="ec-btn-primary" disabled={!title || save.isPending} onClick={() => save.mutate()}>
            <Save size={14} />{save.isPending ? 'Saving…' : 'Save'}
          </button>
          {selectedId && (
            <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete document?')) remove.mutate(selectedId); }}>
              <Trash2 size={14} />
            </button>
          )}
        </div>
        {preview ? (
          <div className="prose-sm max-w-none rounded-lg border border-border bg-surface-elevated p-4 text-sm">
            {content.split('\n\n').map((p, i) => <p key={i} className="mb-3 whitespace-pre-wrap">{p}</p>)}
          </div>
        ) : (
          <textarea className="ec-input font-mono text-sm" rows={20} value={content}
                    onChange={(e) => { setContent(e.target.value); setDirty(true); }}
                    placeholder="Write your document. Two newlines = new paragraph." />
        )}
        {dirty && <p className="text-xs text-amber-500">Unsaved changes.</p>}
      </div>
    </div>
  );
}
