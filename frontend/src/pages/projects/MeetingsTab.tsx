import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, X, Edit3, FileText, Save } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';
import { Meeting, MeetingMinute, Project } from './types';

const STATUSES = ['scheduled', 'in_progress', 'completed', 'cancelled'] as const;
const STATUS_BADGE: Record<string, string> = {
  scheduled: 'ec-badge-blue', in_progress: 'ec-badge-amber',
  completed: 'ec-badge-green', cancelled: 'ec-badge-rose',
};

export function MeetingsTab() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Meeting | null>(null);
  const [selectedMeetingId, setSelectedMeetingId] = useState<string | null>(null);

  const projects = useQuery({
    queryKey: ['projects', 'list'],
    queryFn: async () => (await api.get<Project[]>('/projects/projects')).data,
  });
  const meetings = useQuery({
    queryKey: ['projects', 'meetings'],
    queryFn: async () => (await api.get<Meeting[]>('/projects/meetings')).data,
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/projects/meetings/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects', 'meetings'] }),
  });

  const selected = meetings.data?.find((m) => m.id === selectedMeetingId);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Meetings & Minutes</p>
          <p className="text-sm text-ink-muted">Schedule meetings and record minutes inline.</p>
        </div>
        <button className="ec-btn-primary" onClick={() => { setEditing(null); setShowForm(true); }}><Plus size={16} /> Schedule meeting</button>
      </div>

      {(showForm || editing) && (
        <MeetingForm
          editing={editing}
          projects={projects.data ?? []}
          onSaved={() => { setShowForm(false); setEditing(null); qc.invalidateQueries({ queryKey: ['projects', 'meetings'] }); }}
          onCancel={() => { setShowForm(false); setEditing(null); }}
        />
      )}

      <div className="grid gap-3 md:grid-cols-[1fr_1fr]">
        <div className="ec-card overflow-x-auto">
          <div className="border-b border-border bg-surface-muted px-3 py-2 text-sm font-semibold">Upcoming &amp; recent</div>
          <table className="ec-table">
            <thead><tr><th>Title</th><th>When</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {meetings.data?.length ? meetings.data.map((m) => (
                <tr key={m.id} className={selectedMeetingId === m.id ? 'bg-surface-muted' : ''}>
                  <td className="font-medium cursor-pointer" onClick={() => setSelectedMeetingId(m.id)}>{m.title}</td>
                  <td className="text-xs">{formatDateTime(m.starts_at)}</td>
                  <td><span className={STATUS_BADGE[m.status] ?? 'ec-badge'}>{m.status}</span></td>
                  <td className="text-right whitespace-nowrap">
                    <button className="ec-btn-ghost" onClick={() => setEditing(m)}><Edit3 size={14} /></button>
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete meeting?')) remove.mutate(m.id); }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              )) : <tr><td colSpan={4} className="py-6 text-center text-ink-muted">No meetings yet.</td></tr>}
            </tbody>
          </table>
        </div>

        {selected ? (
          <MinutesPanel meeting={selected} projects={projects.data ?? []} />
        ) : (
          <div className="ec-card p-6 text-sm text-ink-muted">
            <p>Select a meeting from the list to view or record minutes.</p>
          </div>
        )}
      </div>
    </div>
  );
}

function MeetingForm({ editing, projects, onSaved, onCancel }: {
  editing: Meeting | null; projects: Project[]; onSaved: () => void; onCancel: () => void;
}) {
  const isoLocal = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  const [title, setTitle] = useState(editing?.title ?? '');
  const [projectId, setProjectId] = useState(editing?.project_id ?? '');
  const [startsAt, setStartsAt] = useState(editing?.starts_at ? isoLocal(new Date(editing.starts_at)) : isoLocal(new Date()));
  const [endsAt, setEndsAt] = useState(editing?.ends_at ? isoLocal(new Date(editing.ends_at)) : isoLocal(new Date(Date.now() + 60 * 60000)));
  const [location, setLocation] = useState(editing?.location ?? '');
  const [meetingUrl, setMeetingUrl] = useState(editing?.meeting_url ?? '');
  const [agenda, setAgenda] = useState(editing?.agenda ?? '');
  const [attendees, setAttendees] = useState(editing?.attendees ?? '');
  const [status, setStatus] = useState(editing?.status ?? 'scheduled');

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        title, project_id: projectId || null,
        starts_at: new Date(startsAt).toISOString(),
        ends_at: endsAt ? new Date(endsAt).toISOString() : null,
        location: location || null, meeting_url: meetingUrl || null,
        agenda, attendees, status,
      };
      if (editing) return (await api.patch(`/projects/meetings/${editing.id}`, body)).data;
      return (await api.post('/projects/meetings', body)).data;
    },
    onSuccess: () => { toast.success('Saved'); onSaved(); },
    onError: () => toast.error('Save failed'),
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? 'Edit meeting' : 'Schedule meeting'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div className="md:col-span-2"><label className="ec-label">Title</label><input className="ec-input" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
        <div><label className="ec-label">Project</label>
          <select className="ec-input" value={projectId ?? ''} onChange={(e) => setProjectId(e.target.value)}>
            <option value="">—</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Starts at</label><input type="datetime-local" className="ec-input" value={startsAt} onChange={(e) => setStartsAt(e.target.value)} /></div>
        <div><label className="ec-label">Ends at</label><input type="datetime-local" className="ec-input" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} /></div>
        <div><label className="ec-label">Status</label>
          <select className="ec-input" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Location</label><input className="ec-input" value={location ?? ''} onChange={(e) => setLocation(e.target.value)} /></div>
        <div className="md:col-span-2"><label className="ec-label">Meeting URL</label><input className="ec-input" value={meetingUrl ?? ''} onChange={(e) => setMeetingUrl(e.target.value)} placeholder="https://..." /></div>
        <div className="md:col-span-3"><label className="ec-label">Attendees</label><input className="ec-input" value={attendees} onChange={(e) => setAttendees(e.target.value)} placeholder="Alice, Bob, Charlie" /></div>
        <div className="md:col-span-3"><label className="ec-label">Agenda</label><textarea className="ec-input" rows={3} value={agenda} onChange={(e) => setAgenda(e.target.value)} /></div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!title || save.isPending} onClick={() => save.mutate()}>{editing ? 'Save' : 'Schedule'}</button>
      </div>
    </div>
  );
}

function MinutesPanel({ meeting, projects }: { meeting: Meeting; projects: Project[] }) {
  const qc = useQueryClient();
  const minutes = useQuery({
    queryKey: ['projects', 'minutes', meeting.id],
    queryFn: async () => (await api.get<MeetingMinute[]>(`/projects/meetings/${meeting.id}/minutes`)).data,
  });

  const [body, setBody] = useState('');
  const [decisions, setDecisions] = useState('');
  const [actions, setActions] = useState('');

  const add = useMutation({
    mutationFn: async () => (await api.post(`/projects/meetings/${meeting.id}/minutes`, {
      body, decisions, action_items: actions,
    })).data,
    onSuccess: () => {
      toast.success('Minutes recorded');
      setBody(''); setDecisions(''); setActions('');
      qc.invalidateQueries({ queryKey: ['projects', 'minutes', meeting.id] });
    },
    onError: () => toast.error('Failed to record'),
  });

  const project = projects.find((p) => p.id === meeting.project_id);

  return (
    <div className="ec-card overflow-hidden">
      <div className="border-b border-border bg-surface-muted px-4 py-3">
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-brand-600" />
          <h3 className="text-base font-semibold">{meeting.title}</h3>
        </div>
        <p className="mt-0.5 text-xs text-ink-muted">
          {formatDateTime(meeting.starts_at)}{meeting.ends_at && ` → ${formatDateTime(meeting.ends_at)}`}
          {project && ` · ${project.name}`}
        </p>
        {meeting.attendees && <p className="mt-1 text-xs">Attendees: {meeting.attendees}</p>}
        {meeting.location && <p className="text-xs">Location: {meeting.location}</p>}
        {meeting.meeting_url && <a href={meeting.meeting_url} className="text-xs text-brand-600 hover:underline" target="_blank" rel="noreferrer">Join: {meeting.meeting_url}</a>}
        {meeting.agenda && <div className="mt-2"><p className="text-xs font-semibold text-ink-muted">AGENDA</p><pre className="whitespace-pre-wrap text-xs">{meeting.agenda}</pre></div>}
      </div>

      <div className="p-4 space-y-3">
        <div>
          <label className="ec-label">Discussion notes</label>
          <textarea className="ec-input" rows={3} value={body} onChange={(e) => setBody(e.target.value)} />
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="ec-label">Decisions</label>
            <textarea className="ec-input" rows={3} value={decisions} onChange={(e) => setDecisions(e.target.value)} placeholder="Key decisions made…" />
          </div>
          <div>
            <label className="ec-label">Action items</label>
            <textarea className="ec-input" rows={3} value={actions} onChange={(e) => setActions(e.target.value)} placeholder="Owner — task — due date" />
          </div>
        </div>
        <div className="flex justify-end">
          <button className="ec-btn-primary" disabled={(!body && !decisions && !actions) || add.isPending} onClick={() => add.mutate()}>
            <Save size={14} /> Record minutes
          </button>
        </div>
      </div>

      <div className="border-t border-border">
        <div className="bg-surface-muted px-4 py-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">
          Recorded minutes ({minutes.data?.length ?? 0})
        </div>
        <div className="max-h-[300px] overflow-y-auto divide-y divide-border/60">
          {minutes.data?.length ? minutes.data.map((m) => (
            <div key={m.id} className="p-3 text-sm">
              {m.body && <p>{m.body}</p>}
              {m.decisions && <p className="mt-1 text-xs"><strong>Decisions:</strong> {m.decisions}</p>}
              {m.action_items && <p className="mt-1 text-xs"><strong>Actions:</strong> {m.action_items}</p>}
            </div>
          )) : <p className="p-4 text-center text-xs text-ink-muted">No minutes recorded yet.</p>}
        </div>
      </div>
    </div>
  );
}
