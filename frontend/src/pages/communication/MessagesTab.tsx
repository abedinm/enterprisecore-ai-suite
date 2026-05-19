import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Plus, Send, MessageSquare } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';

type Thread = { id: string; title: string; created_at: string };
type Message = { id: string; thread_id: string; sender_id: string | null; body: string; created_at: string };

export function MessagesTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');

  const threads = useQuery({
    queryKey: ['comm', 'threads'],
    queryFn: async () => (await api.get<Thread[]>('/communication/threads')).data,
  });
  useEffect(() => { if (threads.data?.length && !selectedId) setSelectedId(threads.data[0].id); }, [threads.data, selectedId]);

  const messages = useQuery({
    enabled: !!selectedId,
    queryKey: ['comm', 'threads', selectedId, 'messages'],
    queryFn: async () => (await api.get<Message[]>(`/communication/threads/${selectedId}/messages`)).data,
  });

  const newThread = useMutation({
    mutationFn: async (title: string) => (await api.post<Thread>('/communication/threads', { title })).data,
    onSuccess: (t) => { setShow(false); setSelectedId(t.id); qc.invalidateQueries({ queryKey: ['comm', 'threads'] }); },
  });
  const send = useMutation({
    mutationFn: async () => (await api.post<Message>(`/communication/threads/${selectedId}/messages`, { body: draft })).data,
    onSuccess: () => { setDraft(''); qc.invalidateQueries({ queryKey: ['comm', 'threads', selectedId, 'messages'] }); },
  });

  return (
    <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
      <div className="ec-card p-3 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">Threads</p>
          <button className="ec-btn-primary !py-1 !px-2" onClick={() => setShow((v) => !v)}><Plus size={14} /></button>
        </div>
        {show && <NewThread onCreate={(t) => newThread.mutate(t)} />}
        <ul className="max-h-[60vh] overflow-y-auto space-y-1">
          {threads.data?.length ? threads.data.map((t) => (
            <li key={t.id}>
              <button onClick={() => setSelectedId(t.id)}
                className={`block w-full rounded-md px-3 py-2 text-left text-sm ${selectedId === t.id ? 'bg-brand-600 text-white' : 'hover:bg-surface-muted'}`}>
                <p className="truncate font-medium">{t.title}</p>
                <p className={`text-xs ${selectedId === t.id ? 'text-white/70' : 'text-ink-muted'}`}>{formatDateTime(t.created_at)}</p>
              </button>
            </li>
          )) : <li className="px-3 py-6 text-center text-sm text-ink-muted">No threads.</li>}
        </ul>
      </div>

      <div className="ec-card flex h-[70vh] flex-col">
        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          {messages.data?.length ? messages.data.map((m) => (
            <div key={m.id} className="flex items-start gap-3">
              <div className="grid h-8 w-8 place-items-center rounded-full bg-brand-600/10 text-brand-600">
                <MessageSquare size={14} />
              </div>
              <div className="flex-1">
                <p className="text-xs text-ink-muted">{formatDateTime(m.created_at)}</p>
                <p className="whitespace-pre-wrap text-sm">{m.body}</p>
              </div>
            </div>
          )) : <p className="grid h-full place-items-center text-sm text-ink-muted">No messages yet.</p>}
        </div>
        {selectedId && (
          <div className="flex gap-2 border-t border-border p-3">
            <textarea className="ec-input" rows={2} value={draft} placeholder="Type a message…" onChange={(e) => setDraft(e.target.value)} />
            <button className="ec-btn-primary" disabled={!draft || send.isPending} onClick={() => send.mutate()}><Send size={14} />Send</button>
          </div>
        )}
      </div>
    </div>
  );
}

function NewThread({ onCreate }: { onCreate: (title: string) => void }) {
  const [t, setT] = useState('');
  return (
    <div className="flex gap-1">
      <input className="ec-input !py-1" value={t} onChange={(e) => setT(e.target.value)} placeholder="Thread title" />
      <button className="ec-btn-primary !py-1 !text-xs" disabled={!t} onClick={() => { onCreate(t); setT(''); }}>Create</button>
    </div>
  );
}
