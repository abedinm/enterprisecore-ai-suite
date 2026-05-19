import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Video } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';

type Meeting = {
  id: string; project_id: string | null; title: string;
  starts_at: string; ends_at: string | null; location: string | null;
  meeting_url: string | null; agenda: string; status: string;
};

export function MeetingsTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const { data } = useQuery({
    queryKey: ['projects', 'meetings'],
    queryFn: async () => (await api.get<Meeting[]>('/projects/meetings')).data,
  });

  const [title, setTitle] = useState('');
  const [starts, setStarts] = useState(new Date().toISOString().slice(0, 16));
  const [url, setUrl] = useState('');
  const save = useMutation({
    mutationFn: async () => (await api.post('/projects/meetings', {
      title, starts_at: new Date(starts).toISOString(), meeting_url: url || null,
    })).data,
    onSuccess: () => { setShow(false); setTitle(''); qc.invalidateQueries({ queryKey: ['projects', 'meetings'] }); },
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-muted">{data?.length ?? 0} meetings</p>
        <button className="ec-btn-primary" onClick={() => setShow((v) => !v)}>
          <Plus size={16} /> {show ? 'Close' : 'Schedule meeting'}
        </button>
      </div>
      {show && (
        <div className="rounded-xl border border-border bg-surface-muted p-4 grid gap-3 md:grid-cols-3">
          <div className="md:col-span-3"><label className="ec-label">Title</label><input className="ec-input" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
          <div><label className="ec-label">Starts at</label><input type="datetime-local" className="ec-input" value={starts} onChange={(e) => setStarts(e.target.value)} /></div>
          <div className="md:col-span-2"><label className="ec-label">Meeting URL (Zoom / Meet / Teams)</label><input className="ec-input" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} /></div>
          <div className="md:col-span-3 flex justify-end">
            <button className="ec-btn-primary" disabled={!title || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save meeting'}</button>
          </div>
        </div>
      )}
      <table className="ec-table">
        <thead><tr><th>Title</th><th>When</th><th>Link</th><th>Status</th></tr></thead>
        <tbody>
          {data?.length ? data.map((m) => (
            <tr key={m.id}>
              <td className="font-medium">{m.title}</td>
              <td>{formatDateTime(m.starts_at)}</td>
              <td>{m.meeting_url ? <a href={m.meeting_url} target="_blank" rel="noreferrer" className="text-brand-600 hover:underline inline-flex items-center gap-1"><Video size={14} />Join</a> : '—'}</td>
              <td><span className="ec-badge ec-badge-blue">{m.status}</span></td>
            </tr>
          )) : <tr><td colSpan={4} className="py-8 text-center text-ink-muted">No meetings scheduled.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
