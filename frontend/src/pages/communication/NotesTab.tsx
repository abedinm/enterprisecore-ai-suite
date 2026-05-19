import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Plus, Save, StickyNote, Search } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';

type Note = { id: string; title: string; body: string; visibility: string; updated_at: string; created_at: string };

export function NotesTab() {
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [visibility, setVisibility] = useState('team');
  const [dirty, setDirty] = useState(false);

  const notes = useQuery({
    queryKey: ['comm', 'notes', q],
    queryFn: async () => (await api.get<Note[]>('/communication/notes', { params: q ? { q } : {} })).data,
  });
  useEffect(() => { if (notes.data?.length && !selectedId) setSelectedId(notes.data[0].id); }, [notes.data, selectedId]);
  const current = notes.data?.find((n) => n.id === selectedId);
  useEffect(() => { if (current && !dirty) { setTitle(current.title); setBody(current.body); setVisibility(current.visibility); } }, [current, dirty]);

  const save = useMutation({
    mutationFn: async () => {
      const data = { title, body, visibility };
      if (selectedId) return (await api.patch<Note>(`/communication/notes/${selectedId}`, data)).data;
      return (await api.post<Note>('/communication/notes', data)).data;
    },
    onSuccess: (n) => { setDirty(false); setSelectedId(n.id); qc.invalidateQueries({ queryKey: ['comm', 'notes'] }); },
  });

  function newNote() { setSelectedId(null); setTitle('New note'); setBody(''); setVisibility('team'); setDirty(true); }

  return (
    <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
      <div className="ec-card p-3 space-y-2">
        <div className="flex gap-2">
          <div className="relative grow">
            <Search size={12} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-ink-subtle" />
            <input className="ec-input !py-1 pl-7" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search…" />
          </div>
          <button className="ec-btn-primary !py-1 !px-2" onClick={newNote}><Plus size={14} /></button>
        </div>
        <ul className="max-h-[60vh] overflow-y-auto space-y-1">
          {notes.data?.length ? notes.data.map((n) => (
            <li key={n.id}>
              <button onClick={() => { setSelectedId(n.id); setDirty(false); }}
                className={`block w-full rounded-md px-3 py-2 text-left text-sm ${selectedId === n.id ? 'bg-brand-600 text-white' : 'hover:bg-surface-muted'}`}>
                <p className="truncate font-medium">{n.title}</p>
                <p className={`text-xs ${selectedId === n.id ? 'text-white/70' : 'text-ink-muted'}`}>{formatDateTime(n.updated_at)}</p>
              </button>
            </li>
          )) : <li className="px-3 py-6 text-center text-sm text-ink-muted">No notes.</li>}
        </ul>
      </div>

      <div className="ec-card p-5 space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="grow"><label className="ec-label">Title</label><input className="ec-input" value={title} onChange={(e) => { setTitle(e.target.value); setDirty(true); }} /></div>
          <div><label className="ec-label">Visibility</label>
            <select className="ec-input" value={visibility} onChange={(e) => { setVisibility(e.target.value); setDirty(true); }}>
              <option value="private">private</option>
              <option value="team">team</option>
              <option value="public">public</option>
            </select>
          </div>
          <button className="ec-btn-primary" disabled={!title || save.isPending} onClick={() => save.mutate()}><Save size={14} />{save.isPending ? 'Saving…' : 'Save'}</button>
        </div>
        <textarea className="ec-input font-mono text-sm" rows={20} value={body}
          onChange={(e) => { setBody(e.target.value); setDirty(true); }}
          placeholder="Markdown supported (rendered as plain text in this offline build)." />
        <p className="flex items-center gap-2 text-xs text-ink-muted"><StickyNote size={12} />{dirty ? 'Unsaved changes' : 'Saved'}</p>
      </div>
    </div>
  );
}
