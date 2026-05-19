import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Plus, Trash2, Edit3, X, Check, Search } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/utils';

export type Employee = {
  id: string; employee_code: string; full_name: string;
  email: string | null; department: string | null; title: string | null;
  hire_date: string | null; salary: string; status: string;
};

const STATUSES = ['active', 'on_leave', 'terminated', 'probation'];
const STATUS_BADGE: Record<string, string> = {
  active: 'ec-badge-green', on_leave: 'ec-badge-amber',
  terminated: 'ec-badge-rose', probation: 'ec-badge-blue',
};

export function EmployeesTab() {
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Employee | null>(null);

  const employees = useQuery({
    queryKey: ['hr', 'employees', q, statusFilter],
    queryFn: async () => (await api.get<Employee[]>('/hr/employees', {
      params: { ...(q ? { q } : {}), ...(statusFilter ? { status: statusFilter } : {}) },
    })).data,
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/hr/employees/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hr', 'employees'] }),
  });

  const totals = useMemo(() => {
    const acc: Record<string, number> = {};
    (employees.data ?? []).forEach((e) => { acc[e.status] = (acc[e.status] ?? 0) + 1; });
    return acc;
  }, [employees.data]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Employees</p>
          <p className="text-sm text-ink-muted">{employees.data?.length ?? 0} records</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div className="relative">
            <label className="ec-label">Search</label>
            <Search size={14} className="pointer-events-none absolute left-3 top-[34px] text-ink-subtle" />
            <input className="ec-input pl-9 !w-56" placeholder="name, email, code" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div>
            <label className="ec-label">Status</label>
            <select className="ec-input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <button className="ec-btn-primary" onClick={() => { setEditing(null); setShowForm((v) => !v); }}>
            <Plus size={16} /> {showForm && !editing ? 'Close' : 'New employee'}
          </button>
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-4">
        {STATUSES.map((s) => (
          <div key={s} className="ec-card p-3">
            <p className="text-[10px] uppercase tracking-wider text-ink-muted">{s.replace('_', ' ')}</p>
            <p className="text-xl font-semibold">{totals[s] ?? 0}</p>
          </div>
        ))}
      </div>

      {(showForm || editing) && (
        <EmployeeForm editing={editing}
          onSaved={() => { setShowForm(false); setEditing(null); qc.invalidateQueries({ queryKey: ['hr', 'employees'] }); }}
          onCancel={() => { setShowForm(false); setEditing(null); }} />
      )}

      <div className="ec-card overflow-x-auto">
        <table className="ec-table">
          <thead><tr><th>Code</th><th>Name</th><th>Email</th><th>Department</th><th>Title</th><th>Hire date</th><th>Salary</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {employees.data?.length ? employees.data.map((e) => (
              <tr key={e.id}>
                <td className="font-mono text-xs">{e.employee_code}</td>
                <td className="font-medium">{e.full_name}</td>
                <td>{e.email ?? '—'}</td>
                <td>{e.department ?? '—'}</td>
                <td>{e.title ?? '—'}</td>
                <td>{formatDate(e.hire_date)}</td>
                <td>{formatCurrency(e.salary)}</td>
                <td><span className={`ec-badge ${STATUS_BADGE[e.status] ?? 'ec-badge'}`}>{e.status}</span></td>
                <td className="space-x-1 whitespace-nowrap text-right">
                  <button className="ec-btn-ghost" onClick={() => { setEditing(e); setShowForm(true); }}><Edit3 size={16} /></button>
                  <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete ' + e.full_name + '?')) remove.mutate(e.id); }}><Trash2 size={16} /></button>
                </td>
              </tr>
            )) : <tr><td colSpan={9} className="py-10 text-center text-ink-muted">No employees match.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EmployeeForm({ editing, onSaved, onCancel }: { editing: Employee | null; onSaved: () => void; onCancel: () => void }) {
  const [code, setCode] = useState(editing?.employee_code ?? '');
  const [name, setName] = useState(editing?.full_name ?? '');
  const [email, setEmail] = useState(editing?.email ?? '');
  const [department, setDepartment] = useState(editing?.department ?? '');
  const [title, setTitle] = useState(editing?.title ?? '');
  const [hireDate, setHireDate] = useState(editing?.hire_date ?? new Date().toISOString().slice(0, 10));
  const [salary, setSalary] = useState(editing ? parseFloat(editing.salary) : 50000);
  const [status, setStatus] = useState(editing?.status ?? 'active');

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        employee_code: code, full_name: name, email: email || null,
        department: department || null, title: title || null,
        hire_date: hireDate || null, salary, status,
      };
      if (editing) return (await api.patch(`/hr/employees/${editing.id}`, body)).data;
      return (await api.post('/hr/employees', body)).data;
    },
    onSuccess: onSaved,
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? `Edit ${editing.full_name}` : 'New employee'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <div><label className="ec-label">Code</label><input className="ec-input" value={code} onChange={(e) => setCode(e.target.value)} /></div>
        <div className="md:col-span-2"><label className="ec-label">Full name</label><input className="ec-input" value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div><label className="ec-label">Status</label>
          <select className="ec-input" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Email</label><input className="ec-input" value={email ?? ''} onChange={(e) => setEmail(e.target.value)} /></div>
        <div><label className="ec-label">Department</label><input className="ec-input" value={department ?? ''} onChange={(e) => setDepartment(e.target.value)} /></div>
        <div><label className="ec-label">Title</label><input className="ec-input" value={title ?? ''} onChange={(e) => setTitle(e.target.value)} /></div>
        <div><label className="ec-label">Hire date</label><input type="date" className="ec-input" value={hireDate ?? ''} onChange={(e) => setHireDate(e.target.value)} /></div>
        <div><label className="ec-label">Annual salary</label><input type="number" className="ec-input" value={salary} onChange={(e) => setSalary(Number(e.target.value))} /></div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!code || !name || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? 'Saving…' : (editing ? <><Check size={14} /> Save changes</> : <>Create</>)}
        </button>
      </div>
    </div>
  );
}
