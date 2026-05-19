import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { MessageSquare, Plus } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';

type Feedback = { id: string; subject: string; category: string; body: string; created_at: string };

export function FeedbackTab() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ['communication', 'feedback'],
    queryFn: async () => (await api.get<Feedback[]>('/communication/feedback')).data,
  });
  const [show, setShow] = useState(false);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [category, setCategory] = useState('general');
  const save = useMutation({
    mutationFn: async () => (await api.post('/communication/feedback', { subject, body, category })).data,
    onSuccess: () => { setShow(false); setSubject(''); setBody(''); qc.invalidateQueries({ queryKey: ['communication', 'feedback'] }); },
  });
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><MessageSquare size={14} />Feedback</p>
          <p className="text-sm text-ink-muted">{data?.length ?? 0} entries</p>
        </div>
        <button className="ec-btn-primary" onClick={() => setShow((v) => !v)}><Plus size={14} />{show ? 'Close' : 'Submit feedback'}</button>
      </div>
      {show && (
        <div className="rounded-xl border border-border bg-surface-muted p-4 grid gap-3 md:grid-cols-2">
          <div><label className="ec-label">Subject</label><input className="ec-input" value={subject} onChange={(e) => setSubject(e.target.value)} /></div>
          <div><label className="ec-label">Category</label>
            <select className="ec-input" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="general">General</option><option value="bug">Bug</option>
              <option value="feature">Feature request</option><option value="praise">Praise</option>
              <option value="complaint">Complaint</option>
            </select>
          </div>
          <div className="md:col-span-2"><label className="ec-label">Message</label>
            <textarea className="ec-input min-h-[120px]" value={body} onChange={(e) => setBody(e.target.value)} /></div>
          <div className="md:col-span-2 flex justify-end">
            <button className="ec-btn-primary" disabled={!subject || !body || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Submit'}</button>
          </div>
        </div>
      )}
      <table className="ec-table">
        <thead><tr><th>When</th><th>Subject</th><th>Category</th><th>Body</th></tr></thead>
        <tbody>
          {data?.length ? data.map((f) => (
            <tr key={f.id}>
              <td className="whitespace-nowrap text-xs">{formatDateTime(f.created_at)}</td>
              <td className="font-medium">{f.subject}</td>
              <td><span className="ec-badge ec-badge-blue">{f.category}</span></td>
              <td className="text-sm text-ink-muted truncate max-w-md">{f.body}</td>
            </tr>
          )) : <tr><td colSpan={4} className="py-8 text-center text-ink-muted">No feedback yet.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
