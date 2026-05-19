import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Mail, Phone, MessageSquare, Calendar, Video } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';
import type { Contact } from './CustomersTab';

type Comm = { id: string; contact_id: string | null; channel: string; subject: string | null; body: string; created_at: string };

const CHANNELS = [
  { value: 'email', label: 'Email', icon: Mail },
  { value: 'call', label: 'Call', icon: Phone },
  { value: 'meeting', label: 'Meeting', icon: Calendar },
  { value: 'video', label: 'Video', icon: Video },
  { value: 'note', label: 'Note', icon: MessageSquare },
];
const CHANNEL_ICON: Record<string, typeof Mail> = Object.fromEntries(CHANNELS.map((c) => [c.value, c.icon]));

export function CommLogTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const [contactFilter, setContactFilter] = useState('');

  const comms = useQuery({
    queryKey: ['crm', 'communications', contactFilter],
    queryFn: async () => (await api.get<Comm[]>('/crm/communications', { params: contactFilter ? { contact_id: contactFilter } : {} })).data,
  });
  const contacts = useQuery({
    queryKey: ['crm', 'contacts'],
    queryFn: async () => (await api.get<Contact[]>('/crm/contacts')).data,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/crm/communications/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['crm', 'communications'] }),
  });

  const byChannel = (comms.data ?? []).reduce<Record<string, number>>((acc, c) => { acc[c.channel] = (acc[c.channel] ?? 0) + 1; return acc; }, {});

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Communication log</p>
          <p className="text-sm text-ink-muted">{comms.data?.length ?? 0} entries</p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="ec-label">Contact</label>
            <select className="ec-input md:!w-56" value={contactFilter} onChange={(e) => setContactFilter(e.target.value)}>
              <option value="">All</option>
              {contacts.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <button className="ec-btn-primary" onClick={() => setShow((v) => !v)}><Plus size={16} />{show ? 'Close' : 'Log entry'}</button>
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-5">
        {CHANNELS.map((ch) => {
          const Icon = ch.icon;
          return (
            <div key={ch.value} className="ec-card p-3">
              <div className="flex items-center justify-between">
                <Icon size={14} className="text-ink-muted" />
                <p className="text-xl font-semibold">{byChannel[ch.value] ?? 0}</p>
              </div>
              <p className="mt-1 text-xs text-ink-muted">{ch.label}</p>
            </div>
          );
        })}
      </div>

      {show && contacts.data && <Form contacts={contacts.data} onSaved={() => { setShow(false); qc.invalidateQueries({ queryKey: ['crm', 'communications'] }); }} />}

      <div className="space-y-2">
        {comms.data?.length ? comms.data.map((c) => {
          const contact = contacts.data?.find((x) => x.id === c.contact_id);
          const Icon = CHANNEL_ICON[c.channel] ?? MessageSquare;
          return (
            <div key={c.id} className="ec-card p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <div className="grid h-9 w-9 place-items-center rounded-full bg-brand-600/10 text-brand-600">
                    <Icon size={16} />
                  </div>
                  <div>
                    <p className="font-medium">{c.subject || `${c.channel} with ${contact?.name ?? 'unknown'}`}</p>
                    <p className="text-xs text-ink-muted">{contact?.name ?? '—'} · {formatDateTime(c.created_at)}</p>
                    {c.body && <p className="mt-2 whitespace-pre-line text-sm">{c.body}</p>}
                  </div>
                </div>
                <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete entry?')) remove.mutate(c.id); }}><Trash2 size={14} /></button>
              </div>
            </div>
          );
        }) : <div className="ec-card p-8 text-center text-sm text-ink-muted">No communications logged.</div>}
      </div>
    </div>
  );
}

function Form({ contacts, onSaved }: { contacts: Contact[]; onSaved: () => void }) {
  const [contactId, setContactId] = useState(contacts[0]?.id ?? '');
  const [channel, setChannel] = useState('email');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const save = useMutation({
    mutationFn: async () => (await api.post('/crm/communications', {
      contact_id: contactId || null, channel, subject: subject || null, body,
    })).data,
    onSuccess: () => { setSubject(''); setBody(''); onSaved(); },
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 space-y-3">
      <div className="grid gap-3 md:grid-cols-4">
        <div className="md:col-span-2"><label className="ec-label">Contact</label>
          <select className="ec-input" value={contactId} onChange={(e) => setContactId(e.target.value)}>
            {contacts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Channel</label>
          <select className="ec-input" value={channel} onChange={(e) => setChannel(e.target.value)}>
            {CHANNELS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Subject</label><input className="ec-input" value={subject} onChange={(e) => setSubject(e.target.value)} /></div>
      </div>
      <div><label className="ec-label">Notes / body</label><textarea rows={3} className="ec-input" value={body} onChange={(e) => setBody(e.target.value)} /></div>
      <div className="flex justify-end"><button className="ec-btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Log entry'}</button></div>
    </div>
  );
}
