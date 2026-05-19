import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Network, Users } from 'lucide-react';
import { api } from '../../lib/api';
import type { Employee } from './EmployeesTab';

type Node = {
  id: string; name: string;
  manager_employee_id: string | null;
  manager_name: string | null;
  headcount: number;
  children: Node[];
};
type Unit = { id: string; name: string; parent_id: string | null; manager_employee_id: string | null };

export function OrgChartTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);

  const tree = useQuery({
    queryKey: ['hr', 'org-chart'],
    queryFn: async () => (await api.get<Node[]>('/hr/org-chart')).data,
  });
  const flat = useQuery({
    queryKey: ['hr', 'org-units'],
    queryFn: async () => (await api.get<Unit[]>('/hr/org-units')).data,
  });
  const employees = useQuery({
    queryKey: ['hr', 'employees'],
    queryFn: async () => (await api.get<Employee[]>('/hr/employees')).data,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/hr/org-units/${id}`)).data,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['hr', 'org-chart'] }); qc.invalidateQueries({ queryKey: ['hr', 'org-units'] }); },
  });

  function refresh() {
    qc.invalidateQueries({ queryKey: ['hr', 'org-chart'] });
    qc.invalidateQueries({ queryKey: ['hr', 'org-units'] });
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Organization chart</p>
          <p className="text-sm text-ink-muted">{flat.data?.length ?? 0} units · headcount sourced from employee.department</p>
        </div>
        <button className="ec-btn-primary" onClick={() => setShow((v) => !v)}><Plus size={16} />{show ? 'Close' : 'New unit'}</button>
      </div>

      {show && flat.data && employees.data && (
        <UnitForm units={flat.data} employees={employees.data}
          onSaved={() => { setShow(false); refresh(); }} />
      )}

      <div className="ec-card p-5">
        <div className="flex items-center gap-2 text-sm font-semibold mb-4"><Network size={16} />Hierarchy</div>
        {tree.data?.length ? <div className="space-y-3">{tree.data.map((n) => <TreeNode key={n.id} node={n} depth={0} onDelete={(id) => remove.mutate(id)} />)}</div>
          : <p className="text-sm text-ink-muted">No org units yet.</p>}
      </div>
    </div>
  );
}

function TreeNode({ node, depth, onDelete }: { node: Node; depth: number; onDelete: (id: string) => void }) {
  return (
    <div style={{ marginLeft: depth * 24 }}>
      <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface-muted px-3 py-2">
        <div className="flex items-center gap-3">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-white">
            <Network size={14} />
          </div>
          <div>
            <p className="font-medium">{node.name}</p>
            <p className="text-xs text-ink-muted">{node.manager_name ? `Manager: ${node.manager_name}` : 'No manager'}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-full bg-surface-elevated px-2 py-0.5 text-xs">
            <Users size={11} /> {node.headcount}
          </span>
          <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete ' + node.name + '?')) onDelete(node.id); }}><Trash2 size={14} /></button>
        </div>
      </div>
      {node.children.length > 0 && (
        <div className="mt-2 space-y-2">
          {node.children.map((c) => <TreeNode key={c.id} node={c} depth={depth + 1} onDelete={onDelete} />)}
        </div>
      )}
    </div>
  );
}

function UnitForm({ units, employees, onSaved }: { units: Unit[]; employees: Employee[]; onSaved: () => void }) {
  const [name, setName] = useState('');
  const [parent, setParent] = useState<string>('');
  const [manager, setManager] = useState<string>('');
  const save = useMutation({
    mutationFn: async () => (await api.post('/hr/org-units', {
      name, parent_id: parent || null, manager_employee_id: manager || null,
    })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 grid gap-3 md:grid-cols-4">
      <div className="md:col-span-2"><label className="ec-label">Unit name</label><input className="ec-input" value={name} onChange={(e) => setName(e.target.value)} /></div>
      <div><label className="ec-label">Parent</label>
        <select className="ec-input" value={parent} onChange={(e) => setParent(e.target.value)}>
          <option value="">— (root)</option>
          {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
      </div>
      <div><label className="ec-label">Manager</label>
        <select className="ec-input" value={manager} onChange={(e) => setManager(e.target.value)}>
          <option value="">—</option>
          {employees.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
        </select>
      </div>
      <div className="md:col-span-4 flex justify-end"><button className="ec-btn-primary" disabled={!name || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save'}</button></div>
    </div>
  );
}
