import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Calendar, Plus } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';

type Event = { id: string; title: string; description: string | null; starts_at: string; ends_at: string | null; location: string | null };

export function CalendarTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const events = useQuery({
    queryKey: ['comm', 'calendar'],
    queryFn: async () => (await api.get<Event[]>('/communication/calendar')).data,
  });

  const grouped = (events.data ?? []).reduce<Record<string, Event[]>>((acc, e) => {
    const day = new Date(e.starts_at).toDateString();
    (acc[day] ??= []).push(e); return acc;
  }, {});
  const days = Object.entries(grouped).sort((a, b) => new Date(a[0]).getTime() - new Date(b[0]).getTime());

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between">
        <div>
          <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><Calendar size={14} />Calendar</p>
          <p className="text-sm text-ink-muted">{events.data?.length ?? 0} events</p>
        </div>
        <button className="ec-btn-primary" onClick={() => setShow((v) => !v)}><Plus size={14} />{show ? 'Close' : 'New event'}</button>
      </div>
      {show && <Form onSaved={() => { setShow(false); qc.invalidateQueries({ queryKey: ['comm', 'calendar'] }); }} />}
      <div className="space-y-4">
        {days.length ? days.map(([day, evs]) => (
          <div key={day} className="ec-card p-4">
            <p className="mb-3 text-sm font-semibold">{day}</p>
            <ul className="space-y-2">
              {evs.map((e) => (
                <li key={e.id} className="flex items-start justify-between gap-3 rounded-md bg-surface-muted p-3">
                  <div>
                    <p className="font-medium">{e.title}</p>
                    {e.description && <p className="text-xs text-ink-muted">{e.description}</p>}
                    {e.location && <p className="text-xs text-ink-muted">📍 {e.location}</p>}
                  </div>
                  <div className="text-right text-xs text-ink-muted whitespace-nowrap">
                    {formatDateTime(e.starts_at)}
                    {e.ends_at && <> → <br />{formatDateTime(e.ends_at)}</>}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )) : <p className="text-sm text-ink-muted">No events on the calendar.</p>}
      </div>
    </div>
  );
}

function Form({ onSaved }: { onSaved: () => void }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [startsAt, setStartsAt] = useState(new Date().toISOString().slice(0, 16));
  const [endsAt, setEndsAt] = useState(new Date(Date.now() + 3600000).toISOString().slice(0, 16));
  const [location, setLocation] = useState('');
  const save = useMutation({
    mutationFn: async () => (await api.post('/communication/calendar', {
      title, description: description || null,
      starts_at: new Date(startsAt).toISOString(),
      ends_at: endsAt ? new Date(endsAt).toISOString() : null,
      location: location || null,
    })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 grid gap-3 md:grid-cols-3">
      <div className="md:col-span-2"><label className="ec-label">Title</label><input className="ec-input" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
      <div><label className="ec-label">Location</label><input className="ec-input" value={location} onChange={(e) => setLocation(e.target.value)} /></div>
      <div><label className="ec-label">Starts</label><input type="datetime-local" className="ec-input" value={startsAt} onChange={(e) => setStartsAt(e.target.value)} /></div>
      <div><label className="ec-label">Ends</label><input type="datetime-local" className="ec-input" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} /></div>
      <div className="md:col-span-3"><label className="ec-label">Description</label><textarea rows={2} className="ec-input" value={description} onChange={(e) => setDescription(e.target.value)} /></div>
      <div className="md:col-span-3 flex justify-end"><button className="ec-btn-primary" disabled={!title || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save'}</button></div>
    </div>
  );
}
