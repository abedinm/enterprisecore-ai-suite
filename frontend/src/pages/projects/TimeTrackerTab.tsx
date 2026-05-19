import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Play, Square, Trash2, Plus, Clock } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';
import { Task, TimeEntry } from './types';

export function TimeTrackerTab() {
  const qc = useQueryClient();
  const [taskId, setTaskId] = useState<string>('');
  const [notes, setNotes] = useState<string>('');
  const [isBillable, setIsBillable] = useState<boolean>(true);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const tasks = useQuery({
    queryKey: ['projects', 'tasks', 'all'],
    queryFn: async () => (await api.get<Task[]>('/projects/tasks')).data,
  });

  const entries = useQuery({
    queryKey: ['projects', 'time-entries'],
    queryFn: async () => (await api.get<TimeEntry[]>('/projects/time-entries')).data,
  });

  const running = entries.data?.find((e) => !e.ended_at);

  const startTimer = useMutation({
    mutationFn: async () => (await api.post('/projects/time-entries', {
      task_id: taskId || null,
      started_at: new Date().toISOString(),
      ended_at: null,
      minutes: 0,
      notes,
      is_billable: isBillable,
    })).data,
    onSuccess: () => {
      toast.success('Timer started');
      qc.invalidateQueries({ queryKey: ['projects', 'time-entries'] });
    },
    onError: () => toast.error('Failed to start'),
  });

  const stopTimer = useMutation({
    mutationFn: async (id: string) => (await api.post(`/projects/time-entries/${id}/stop`)).data,
    onSuccess: () => {
      toast.success('Timer stopped');
      qc.invalidateQueries({ queryKey: ['projects', 'time-entries'] });
    },
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/projects/time-entries/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects', 'time-entries'] }),
  });

  const totalToday = (entries.data ?? [])
    .filter((e) => new Date(e.started_at).toDateString() === new Date().toDateString())
    .reduce((s, e) => s + (e.minutes || 0), 0);
  const totalWeek = (entries.data ?? [])
    .filter((e) => {
      const d = new Date(e.started_at);
      const now = new Date();
      const diff = (now.getTime() - d.getTime()) / 86400000;
      return diff < 7;
    })
    .reduce((s, e) => s + (e.minutes || 0), 0);
  const billableMinutes = (entries.data ?? []).filter((e) => e.is_billable).reduce((s, e) => s + (e.minutes || 0), 0);

  const runningMinutes = running ? Math.floor((now - new Date(running.started_at).getTime()) / 60000) : 0;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-4">
        <StatCard label="Today" value={fmtHrs(totalToday)} />
        <StatCard label="Last 7 days" value={fmtHrs(totalWeek)} />
        <StatCard label="Billable total" value={fmtHrs(billableMinutes)} />
        <StatCard label="Entries" value={String(entries.data?.length ?? 0)} />
      </div>

      <div className="ec-card p-4">
        <div className="mb-3 flex items-center gap-2">
          <Clock className="text-brand-600" size={18} />
          <p className="text-sm font-semibold">{running ? 'Running timer' : 'Start a new timer'}</p>
        </div>
        {running ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/20 p-4">
            <div>
              <p className="text-sm text-ink-muted">Running on</p>
              <p className="text-lg font-semibold">{tasks.data?.find((t) => t.id === running.task_id)?.title ?? 'Untitled'}</p>
              <p className="text-xs text-ink-muted">Started {formatDateTime(running.started_at)}</p>
            </div>
            <div className="text-right">
              <p className="font-mono text-3xl tabular-nums">{fmtHrs(runningMinutes)}</p>
              <button className="ec-btn-danger mt-2" onClick={() => stopTimer.mutate(running.id)}><Square size={14} /> Stop</button>
            </div>
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
            <div>
              <label className="ec-label">Task</label>
              <select className="ec-input" value={taskId} onChange={(e) => setTaskId(e.target.value)}>
                <option value="">No task</option>
                {tasks.data?.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
              </select>
            </div>
            <div>
              <label className="ec-label">Notes</label>
              <input className="ec-input" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="What are you working on?" />
            </div>
            <div className="flex flex-col">
              <label className="ec-label">&nbsp;</label>
              <div className="flex items-center gap-2">
                <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={isBillable} onChange={(e) => setIsBillable(e.target.checked)} /> Billable</label>
                <button className="ec-btn-primary" disabled={startTimer.isPending} onClick={() => startTimer.mutate()}><Play size={14} /> Start</button>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="ec-card p-4">
        <p className="mb-3 text-sm font-semibold">Manual entry</p>
        <ManualEntryForm tasks={tasks.data ?? []} onSaved={() => qc.invalidateQueries({ queryKey: ['projects', 'time-entries'] })} />
      </div>

      <div className="ec-card overflow-x-auto">
        <table className="ec-table">
          <thead>
            <tr><th>Task</th><th>Started</th><th>Ended</th><th>Duration</th><th>Billable</th><th>Notes</th><th></th></tr>
          </thead>
          <tbody>
            {entries.data?.length ? entries.data.map((e) => (
              <tr key={e.id}>
                <td>{tasks.data?.find((t) => t.id === e.task_id)?.title ?? '—'}</td>
                <td>{formatDateTime(e.started_at)}</td>
                <td>{e.ended_at ? formatDateTime(e.ended_at) : <span className="text-emerald-600">running</span>}</td>
                <td>{fmtHrs(e.minutes)}</td>
                <td>{e.is_billable ? <span className="ec-badge-green">yes</span> : <span className="ec-badge">no</span>}</td>
                <td className="max-w-xs truncate">{e.notes}</td>
                <td className="text-right">
                  {!e.ended_at && <button className="ec-btn-ghost" onClick={() => stopTimer.mutate(e.id)}><Square size={14} /></button>}
                  <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete entry?')) remove.mutate(e.id); }}><Trash2 size={14} /></button>
                </td>
              </tr>
            )) : <tr><td colSpan={7} className="py-10 text-center text-ink-muted">No time entries yet — start a timer or add a manual entry.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function fmtHrs(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}h ${String(m).padStart(2, '0')}m`;
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="ec-card p-3">
      <p className="text-[10px] uppercase tracking-wider text-ink-muted">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function ManualEntryForm({ tasks, onSaved }: { tasks: Task[]; onSaved: () => void }) {
  const today = new Date();
  const isoLocal = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  const [taskId, setTaskId] = useState<string>('');
  const [start, setStart] = useState<string>(isoLocal(new Date(today.getTime() - 60 * 60000)));
  const [end, setEnd] = useState<string>(isoLocal(today));
  const [notes, setNotes] = useState<string>('');
  const [billable, setBillable] = useState<boolean>(true);

  const save = useMutation({
    mutationFn: async () => {
      const startDt = new Date(start).toISOString();
      const endDt = new Date(end).toISOString();
      return (await api.post('/projects/time-entries', {
        task_id: taskId || null,
        started_at: startDt, ended_at: endDt,
        minutes: 0, notes, is_billable: billable,
      })).data;
    },
    onSuccess: () => { toast.success('Entry logged'); setNotes(''); onSaved(); },
    onError: () => toast.error('Failed to save'),
  });

  return (
    <div className="grid gap-2 md:grid-cols-[1fr_180px_180px_1fr_auto_auto]">
      <select className="ec-input" value={taskId} onChange={(e) => setTaskId(e.target.value)}>
        <option value="">No task</option>
        {tasks.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
      </select>
      <input type="datetime-local" className="ec-input" value={start} onChange={(e) => setStart(e.target.value)} />
      <input type="datetime-local" className="ec-input" value={end} onChange={(e) => setEnd(e.target.value)} />
      <input className="ec-input" placeholder="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
      <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={billable} onChange={(e) => setBillable(e.target.checked)} /> Billable</label>
      <button className="ec-btn-primary" disabled={save.isPending} onClick={() => save.mutate()}><Plus size={14} /> Add</button>
    </div>
  );
}
