import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, AlertOctagon } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDate } from '../../lib/utils';
import type { Employee } from './EmployeesTab';

type Record_ = { id: string; employee_id: string; incident_date: string; severity: string; notes: string };

const SEVERITIES = ['verbal', 'written', 'suspension', 'final', 'termination'];
const SEVERITY_BADGE: Record<string, string> = {
  verbal: 'ec-badge-blue', written: 'ec-badge-amber',
  suspension: 'ec-badge-rose', final: 'ec-badge-rose', termination: 'ec-badge-rose',
};

export function DisciplineTab() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [empFilter, setEmpFilter] = useState('');

  const employees = useQuery({
    queryKey: ['hr', 'employees'],
    queryFn: async () => (await api.get<Employee[]>('/hr/employees')).data,
  });
  const records = useQuery({
    queryKey: ['hr', 'discipline', empFilter],
    queryFn: async () => (await api.get<Record_[]>('/hr/disciplinary', { params: empFilter ? { employee_id: empFilter } : {} })).data,
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/hr/disciplinary/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hr', 'discipline'] }),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted">
            <AlertOctagon size={14} className="text-amber-500" /> Disciplinary records (confidential)
          </p>
          <p className="text-sm text-ink-muted">{records.data?.length ?? 0} incidents</p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="ec-label">Employee filter</label>
            <select className="ec-input md:!w-56" value={empFilter} onChange={(e) => setEmpFilter(e.target.value)}>
              <option value="">All</option>
              {employees.data?.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
            </select>
          </div>
          <button className="ec-btn-primary" onClick={() => setShowForm((v) => !v)}><Plus size={16} />{showForm ? 'Close' : 'Record incident'}</button>
        </div>
      </div>

      {showForm && employees.data && (
        <Form employees={employees.data}
          onSaved={() => { setShowForm(false); qc.invalidateQueries({ queryKey: ['hr', 'discipline'] }); }} />
      )}

      <div className="ec-card overflow-hidden">
        <table className="ec-table">
          <thead><tr><th>Date</th><th>Employee</th><th>Severity</th><th>Notes</th><th></th></tr></thead>
          <tbody>
            {records.data?.length ? records.data.map((r) => {
              const emp = employees.data?.find((e) => e.id === r.employee_id);
              return (
                <tr key={r.id}>
                  <td>{formatDate(r.incident_date)}</td>
                  <td className="font-medium">{emp?.full_name ?? '—'}</td>
                  <td><span className={`ec-badge ${SEVERITY_BADGE[r.severity] ?? 'ec-badge'}`}>{r.severity}</span></td>
                  <td className="max-w-md truncate text-xs text-ink-muted" title={r.notes}>{r.notes || '—'}</td>
                  <td className="text-right">
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete incident?')) remove.mutate(r.id); }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={5} className="py-8 text-center text-ink-muted">No incidents recorded.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Form({ employees, onSaved }: { employees: Employee[]; onSaved: () => void }) {
  const [empId, setEmpId] = useState(employees[0]?.id ?? '');
  const [incidentDate, setIncidentDate] = useState(new Date().toISOString().slice(0, 10));
  const [severity, setSeverity] = useState('verbal');
  const [notes, setNotes] = useState('');
  const save = useMutation({
    mutationFn: async () => (await api.post('/hr/disciplinary', {
      employee_id: empId, incident_date: incidentDate, severity, notes,
    })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-4 grid gap-3 md:grid-cols-4">
      <div className="md:col-span-2"><label className="ec-label">Employee</label>
        <select className="ec-input" value={empId} onChange={(e) => setEmpId(e.target.value)}>
          {employees.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
        </select>
      </div>
      <div><label className="ec-label">Incident date</label><input type="date" className="ec-input" value={incidentDate} onChange={(e) => setIncidentDate(e.target.value)} /></div>
      <div><label className="ec-label">Severity</label>
        <select className="ec-input" value={severity} onChange={(e) => setSeverity(e.target.value)}>
          {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <div className="md:col-span-4"><label className="ec-label">Notes</label><textarea rows={3} className="ec-input" value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
      <div className="md:col-span-4 flex justify-end"><button className="ec-btn-primary" disabled={!empId || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Record incident'}</button></div>
    </div>
  );
}
