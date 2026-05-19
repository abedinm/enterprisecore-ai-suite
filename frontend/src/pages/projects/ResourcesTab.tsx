import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit3, X, Check } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/utils';
import { Allocation, Project, Resource } from './types';

export function ResourcesTab() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<'people' | 'allocations'>('people');
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Resource | null>(null);

  const resources = useQuery({
    queryKey: ['projects', 'resources'],
    queryFn: async () => (await api.get<Resource[]>('/projects/resources')).data,
  });
  const projects = useQuery({
    queryKey: ['projects', 'list'],
    queryFn: async () => (await api.get<Project[]>('/projects/projects')).data,
  });
  const allocations = useQuery({
    queryKey: ['projects', 'allocations'],
    queryFn: async () => (await api.get<Allocation[]>('/projects/allocations')).data,
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/projects/resources/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects', 'resources'] }),
  });

  const totalCapacity = (resources.data ?? []).filter((r) => r.is_active)
    .reduce((s, r) => s + Number(r.capacity_hours_per_week), 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Resource Allocator</p>
          <p className="text-sm text-ink-muted">{resources.data?.length ?? 0} resources, {Math.round(totalCapacity)} hrs/week capacity</p>
        </div>
        <div className="flex gap-2">
          <button className={`ec-btn-secondary ${tab === 'people' ? '!bg-brand-600 !text-white' : ''}`} onClick={() => setTab('people')}>People</button>
          <button className={`ec-btn-secondary ${tab === 'allocations' ? '!bg-brand-600 !text-white' : ''}`} onClick={() => setTab('allocations')}>Allocations</button>
          <button className="ec-btn-primary" onClick={() => { setEditing(null); setShowForm(true); }}><Plus size={16} /> Add {tab === 'people' ? 'resource' : 'allocation'}</button>
        </div>
      </div>

      {tab === 'people' && showForm && (
        <ResourceForm
          editing={editing}
          onSaved={() => { setShowForm(false); setEditing(null); qc.invalidateQueries({ queryKey: ['projects', 'resources'] }); }}
          onCancel={() => { setShowForm(false); setEditing(null); }}
        />
      )}
      {tab === 'allocations' && showForm && (
        <AllocationForm
          resources={resources.data ?? []}
          projects={projects.data ?? []}
          onSaved={() => { setShowForm(false); qc.invalidateQueries({ queryKey: ['projects', 'allocations'] }); }}
          onCancel={() => setShowForm(false)}
        />
      )}

      {tab === 'people' && (
        <div className="ec-card overflow-x-auto">
          <table className="ec-table">
            <thead><tr><th>Name</th><th>Role</th><th>Rate</th><th>Capacity</th><th>Skills</th><th>Active</th><th></th></tr></thead>
            <tbody>
              {resources.data?.length ? resources.data.map((r) => (
                <tr key={r.id}>
                  <td className="font-medium">{r.name}</td>
                  <td>{r.role || '—'}</td>
                  <td>{formatCurrency(r.hourly_rate)}</td>
                  <td>{r.capacity_hours_per_week} h/wk</td>
                  <td className="max-w-sm truncate">{r.skills || '—'}</td>
                  <td>{r.is_active ? <span className="ec-badge-green">active</span> : <span className="ec-badge">inactive</span>}</td>
                  <td className="text-right whitespace-nowrap">
                    <button className="ec-btn-ghost" onClick={() => { setEditing(r); setShowForm(true); }}><Edit3 size={14} /></button>
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete resource?')) remove.mutate(r.id); }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              )) : <tr><td colSpan={7} className="py-10 text-center text-ink-muted">No resources yet — add one.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'allocations' && (
        <AllocationGrid
          allocations={allocations.data ?? []}
          resources={resources.data ?? []}
          projects={projects.data ?? []}
          onChange={() => qc.invalidateQueries({ queryKey: ['projects', 'allocations'] })}
        />
      )}
    </div>
  );
}

function ResourceForm({ editing, onSaved, onCancel }: { editing: Resource | null; onSaved: () => void; onCancel: () => void }) {
  const [name, setName] = useState(editing?.name ?? '');
  const [role, setRole] = useState(editing?.role ?? '');
  const [rate, setRate] = useState(editing?.hourly_rate ?? '0');
  const [capacity, setCapacity] = useState(editing?.capacity_hours_per_week ?? '40');
  const [skills, setSkills] = useState(editing?.skills ?? '');
  const [active, setActive] = useState(editing?.is_active ?? true);

  const save = useMutation({
    mutationFn: async () => {
      const body = { name, role, hourly_rate: rate, capacity_hours_per_week: capacity, skills, is_active: active };
      if (editing) return (await api.patch(`/projects/resources/${editing.id}`, body)).data;
      return (await api.post('/projects/resources', body)).data;
    },
    onSuccess: () => { toast.success('Saved'); onSaved(); },
    onError: () => toast.error('Save failed'),
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? 'Edit resource' : 'Add resource'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div><label className="ec-label">Name</label><input className="ec-input" value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div><label className="ec-label">Role</label><input className="ec-input" value={role} onChange={(e) => setRole(e.target.value)} placeholder="Engineer, Designer…" /></div>
        <div><label className="ec-label">Hourly rate</label><input type="number" className="ec-input" value={rate} step="any" onChange={(e) => setRate(e.target.value)} /></div>
        <div><label className="ec-label">Capacity (hrs/week)</label><input type="number" className="ec-input" value={capacity} step="any" onChange={(e) => setCapacity(e.target.value)} /></div>
        <div className="md:col-span-2"><label className="ec-label">Skills</label><input className="ec-input" value={skills} onChange={(e) => setSkills(e.target.value)} placeholder="react, python, devops" /></div>
        <div className="md:col-span-3"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Active</label></div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!name || save.isPending} onClick={() => save.mutate()}>{editing ? 'Save' : 'Add'}</button>
      </div>
    </div>
  );
}

function AllocationForm({ resources, projects, onSaved, onCancel }: { resources: Resource[]; projects: Project[]; onSaved: () => void; onCancel: () => void }) {
  const today = new Date().toISOString().slice(0, 10);
  const [resourceId, setResourceId] = useState(resources[0]?.id ?? '');
  const [projectId, setProjectId] = useState(projects[0]?.id ?? '');
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10));
  const [pct, setPct] = useState('100');
  const [notes, setNotes] = useState('');

  const save = useMutation({
    mutationFn: async () => (await api.post('/projects/allocations', {
      resource_id: resourceId, project_id: projectId,
      start_date: start, end_date: end, allocation_pct: pct, notes,
    })).data,
    onSuccess: () => { toast.success('Allocation created'); onSaved(); },
    onError: () => toast.error('Failed'),
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">New allocation</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div><label className="ec-label">Resource</label>
          <select className="ec-input" value={resourceId} onChange={(e) => setResourceId(e.target.value)}>
            {resources.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Project</label>
          <select className="ec-input" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Allocation %</label><input type="number" className="ec-input" value={pct} step="any" onChange={(e) => setPct(e.target.value)} /></div>
        <div><label className="ec-label">Start</label><input type="date" className="ec-input" value={start} onChange={(e) => setStart(e.target.value)} /></div>
        <div><label className="ec-label">End</label><input type="date" className="ec-input" value={end} onChange={(e) => setEnd(e.target.value)} /></div>
        <div><label className="ec-label">Notes</label><input className="ec-input" value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!resourceId || !projectId || save.isPending} onClick={() => save.mutate()}>Allocate</button>
      </div>
    </div>
  );
}

function AllocationGrid({ allocations, resources, projects, onChange }: { allocations: Allocation[]; resources: Resource[]; projects: Project[]; onChange: () => void }) {
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/projects/allocations/${id}`)).data,
    onSuccess: () => { toast.success('Removed'); onChange(); },
  });

  return (
    <div className="ec-card overflow-x-auto">
      <table className="ec-table">
        <thead><tr><th>Resource</th><th>Project</th><th>Start</th><th>End</th><th>%</th><th>Notes</th><th></th></tr></thead>
        <tbody>
          {allocations.length ? allocations.map((a) => (
            <tr key={a.id}>
              <td className="font-medium">{resources.find((r) => r.id === a.resource_id)?.name ?? '—'}</td>
              <td>{projects.find((p) => p.id === a.project_id)?.name ?? '—'}</td>
              <td>{formatDate(a.start_date)}</td>
              <td>{formatDate(a.end_date)}</td>
              <td>
                <div className="flex items-center gap-2">
                  <div className="h-2 w-16 rounded-full bg-surface-muted">
                    <div className="h-2 rounded-full bg-brand-600" style={{ width: `${Math.min(100, Number(a.allocation_pct))}%` }} />
                  </div>
                  <span className="text-xs">{Math.round(Number(a.allocation_pct))}%</span>
                </div>
              </td>
              <td className="max-w-sm truncate">{a.notes}</td>
              <td className="text-right"><button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Remove allocation?')) remove.mutate(a.id); }}><Trash2 size={14} /></button></td>
            </tr>
          )) : <tr><td colSpan={7} className="py-10 text-center text-ink-muted">No allocations yet.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
