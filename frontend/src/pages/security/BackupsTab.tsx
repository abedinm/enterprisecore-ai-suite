import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Database, Play, Plus } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';

type Schedule = {
  id: string; name: string; cadence: string; target_path: string;
  last_run_at: string | null; is_active: boolean;
};

export function BackupsTab() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ['security', 'backups'],
    queryFn: async () => (await api.get<Schedule[]>('/security/backups')).data,
  });
  const [show, setShow] = useState(false);
  const [name, setName] = useState('Daily DB snapshot');
  const [cadence, setCadence] = useState('daily');
  const [target, setTarget] = useState('storage/backups');

  const save = useMutation({
    mutationFn: async () => (await api.post('/security/backups', { name, cadence, target_path: target, is_active: true })).data,
    onSuccess: () => { setShow(false); qc.invalidateQueries({ queryKey: ['security', 'backups'] }); },
  });
  const run = useMutation({
    mutationFn: async (id: string) => (await api.post(`/security/backups/${id}/run`)).data,
    onSuccess: (d: any) => {
      toast.success(`Backup created: ${(d.size_bytes / 1024).toFixed(1)} KB`);
      qc.invalidateQueries({ queryKey: ['security', 'backups'] });
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-muted">{data?.length ?? 0} schedules</p>
        <button className="ec-btn-primary" onClick={() => setShow((v) => !v)}><Plus size={16} /> {show ? 'Close' : 'New schedule'}</button>
      </div>
      {show && (
        <div className="rounded-xl border border-border bg-surface-muted p-4 grid gap-3 md:grid-cols-3">
          <div><label className="ec-label">Name</label><input className="ec-input" value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div><label className="ec-label">Cadence</label>
            <select className="ec-input" value={cadence} onChange={(e) => setCadence(e.target.value)}>
              <option value="hourly">Hourly</option><option value="daily">Daily</option><option value="weekly">Weekly</option>
            </select>
          </div>
          <div><label className="ec-label">Target path</label><input className="ec-input" value={target} onChange={(e) => setTarget(e.target.value)} /></div>
          <div className="md:col-span-3 flex justify-end">
            <button className="ec-btn-primary" disabled={!name || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save'}</button>
          </div>
        </div>
      )}
      <table className="ec-table">
        <thead><tr><th>Name</th><th>Cadence</th><th>Target</th><th>Last run</th><th></th></tr></thead>
        <tbody>
          {data?.length ? data.map((s) => (
            <tr key={s.id}>
              <td className="font-medium"><div className="flex items-center gap-2"><Database size={14} className="text-ink-muted" />{s.name}</div></td>
              <td>{s.cadence}</td>
              <td className="font-mono text-xs">{s.target_path}</td>
              <td className="text-xs text-ink-muted">{s.last_run_at ? formatDateTime(s.last_run_at) : 'never'}</td>
              <td className="text-right">
                <button className="ec-btn-secondary" disabled={run.isPending} onClick={() => run.mutate(s.id)}><Play size={14} /> Run now</button>
              </td>
            </tr>
          )) : <tr><td colSpan={5} className="py-8 text-center text-ink-muted">No backup schedules.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
