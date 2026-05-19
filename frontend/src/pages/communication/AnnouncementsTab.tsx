import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Megaphone, Plus } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';

type Announcement = { id: string; title: string; body: string; priority: string; created_at: string };

const PRIORITIES = ['info', 'warning', 'critical'];
const PR_COLOR: Record<string, string> = { info: 'border-blue-500/40 bg-blue-500/5', warning: 'border-amber-500/40 bg-amber-500/5', critical: 'border-rose-500/40 bg-rose-500/5' };

export function AnnouncementsTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const items = useQuery({
    queryKey: ['comm', 'announcements'],
    queryFn: async () => (await api.get<Announcement[]>('/communication/announcements')).data,
  });
  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between">
        <div>
          <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><Megaphone size={14} />Announcements</p>
          <p className="text-sm text-ink-muted">{items.data?.length ?? 0} posts</p>
        </div>
        <button className="ec-btn-primary" onClick={() => setShow((v) => !v)}><Plus size={14} />{show ? 'Close' : 'New announcement'}</button>
      </div>
      {show && <Form onSaved={() => { setShow(false); qc.invalidateQueries({ queryKey: ['comm', 'announcements'] }); }} />}
      <div className="space-y-3">
        {items.data?.length ? items.data.map((a) => (
          <div key={a.id} className={`rounded-xl border p-4 ${PR_COLOR[a.priority] ?? 'border-border bg-surface-elevated'}`}>
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">{a.title}</h3>
              <span className="text-xs uppercase text-ink-muted">{a.priority}</span>
            </div>
            <p className="mt-1 text-xs text-ink-muted">{formatDateTime(a.created_at)}</p>
            <p className="mt-2 whitespace-pre-wrap text-sm">{a.body}</p>
          </div>
        )) : <p className="text-sm text-ink-muted">No announcements yet.</p>}
      </div>
    </div>
  );
}

function Form({ onSaved }: { onSaved: () => void }) {
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [priority, setPriority] = useState('info');
  const save = useMutation({
    mutationFn: async () => (await api.post('/communication/announcements', { title, body, priority })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 space-y-3">
      <div className="grid gap-3 md:grid-cols-3">
        <div className="md:col-span-2"><label className="ec-label">Title</label><input className="ec-input" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
        <div><label className="ec-label">Priority</label>
          <select className="ec-input" value={priority} onChange={(e) => setPriority(e.target.value)}>
            {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
      </div>
      <div><label className="ec-label">Body</label><textarea rows={4} className="ec-input" value={body} onChange={(e) => setBody(e.target.value)} /></div>
      <div className="flex justify-end"><button className="ec-btn-primary" disabled={!title || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Posting…' : 'Post'}</button></div>
    </div>
  );
}
