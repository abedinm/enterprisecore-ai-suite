import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit3, Check, X, AlertTriangle } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/utils';

type RP = { id: string; title: string; amount: string; currency: string; cadence: string; next_due_date: string | null };

const CADENCES = ['weekly', 'biweekly', 'monthly', 'quarterly', 'yearly'];

export function RecurringTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);

  const { data } = useQuery({
    queryKey: ['finance', 'recurring'],
    queryFn: async () => (await api.get<RP[]>('/finance/recurring')).data,
  });

  const [editing, setEditing] = useState<string | null>(null);
  const [edit, setEdit] = useState<Partial<RP>>({});

  const update = useMutation({
    mutationFn: async () => (await api.patch(`/finance/recurring/${editing}`, {
      title: edit.title, amount: parseFloat(String(edit.amount ?? '0')),
      currency: edit.currency, cadence: edit.cadence, next_due_date: edit.next_due_date,
    })).data,
    onSuccess: () => { setEditing(null); qc.invalidateQueries({ queryKey: ['finance', 'recurring'] }); },
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/finance/recurring/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['finance', 'recurring'] }),
  });

  const today = new Date().toISOString().slice(0, 10);
  const total = (data ?? []).reduce((s, r) => s + parseFloat(r.amount), 0);
  const overdueCount = (data ?? []).filter((r) => r.next_due_date && r.next_due_date < today).length;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Recurring payments</p>
          <p className="text-sm text-ink-muted">{data?.length ?? 0} subscriptions · {formatCurrency(total)} per cycle</p>
        </div>
        <button className="ec-btn-primary" onClick={() => setShow((v) => !v)}>
          <Plus size={16} /> {show ? 'Close' : 'New recurring payment'}
        </button>
      </div>

      {overdueCount > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/5 px-4 py-2 text-sm">
          <AlertTriangle size={16} className="text-amber-500" />
          <span><strong>{overdueCount}</strong> recurring payment{overdueCount === 1 ? '' : 's'} past due — update or mark them paid.</span>
        </div>
      )}

      {show && <Form onSaved={() => { setShow(false); qc.invalidateQueries({ queryKey: ['finance', 'recurring'] }); }} />}

      <div className="ec-card overflow-hidden">
        <table className="ec-table">
          <thead><tr><th>Title</th><th>Amount</th><th>Currency</th><th>Cadence</th><th>Next due</th><th></th></tr></thead>
          <tbody>
            {data?.length ? data.map((r) => {
              const overdue = r.next_due_date && r.next_due_date < today;
              const isEdit = editing === r.id;
              return (
                <tr key={r.id} className={overdue ? 'bg-amber-500/5' : ''}>
                  {isEdit ? (
                    <>
                      <td><input className="ec-input !py-1" defaultValue={r.title} onChange={(e) => setEdit((s) => ({ ...s, title: e.target.value }))} /></td>
                      <td><input type="number" className="ec-input !py-1" defaultValue={r.amount} onChange={(e) => setEdit((s) => ({ ...s, amount: e.target.value }))} /></td>
                      <td><input className="ec-input !py-1 !w-20" maxLength={3} defaultValue={r.currency} onChange={(e) => setEdit((s) => ({ ...s, currency: e.target.value.toUpperCase() }))} /></td>
                      <td>
                        <select className="ec-input !py-1" defaultValue={r.cadence} onChange={(e) => setEdit((s) => ({ ...s, cadence: e.target.value }))}>
                          {CADENCES.map((c) => <option key={c} value={c}>{c}</option>)}
                        </select>
                      </td>
                      <td><input type="date" className="ec-input !py-1" defaultValue={r.next_due_date ?? ''} onChange={(e) => setEdit((s) => ({ ...s, next_due_date: e.target.value }))} /></td>
                      <td className="text-right whitespace-nowrap">
                        <button className="ec-btn-ghost text-emerald-600" onClick={() => update.mutate()}><Check size={16} /></button>
                        <button className="ec-btn-ghost" onClick={() => setEditing(null)}><X size={16} /></button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="font-medium">{r.title}</td>
                      <td>{formatCurrency(r.amount, r.currency)}</td>
                      <td>{r.currency}</td>
                      <td className="capitalize">{r.cadence}</td>
                      <td className={overdue ? 'font-medium text-amber-500' : ''}>{formatDate(r.next_due_date)}{overdue ? ' (overdue)' : ''}</td>
                      <td className="text-right whitespace-nowrap">
                        <button className="ec-btn-ghost" onClick={() => { setEditing(r.id); setEdit(r); }}><Edit3 size={16} /></button>
                        <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete ' + r.title + '?')) remove.mutate(r.id); }}><Trash2 size={16} /></button>
                      </td>
                    </>
                  )}
                </tr>
              );
            }) : <tr><td colSpan={6} className="py-8 text-center text-ink-muted">No recurring payments configured.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Form({ onSaved }: { onSaved: () => void }) {
  const [title, setTitle] = useState('');
  const [amount, setAmount] = useState(0);
  const [currency, setCurrency] = useState('USD');
  const [cadence, setCadence] = useState('monthly');
  const [next, setNext] = useState(new Date().toISOString().slice(0, 10));
  const save = useMutation({
    mutationFn: async () => (await api.post('/finance/recurring', {
      title, amount, currency, cadence, next_due_date: next,
    })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 grid gap-3 md:grid-cols-5">
      <div className="md:col-span-2"><label className="ec-label">Title</label><input className="ec-input" placeholder="e.g. Office rent" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
      <div><label className="ec-label">Amount</label><input type="number" step="any" className="ec-input" value={amount} onChange={(e) => setAmount(Number(e.target.value))} /></div>
      <div><label className="ec-label">Currency</label><input className="ec-input" maxLength={3} value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} /></div>
      <div>
        <label className="ec-label">Cadence</label>
        <select className="ec-input" value={cadence} onChange={(e) => setCadence(e.target.value)}>
          {CADENCES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <div className="md:col-span-2"><label className="ec-label">Next due</label><input type="date" className="ec-input" value={next} onChange={(e) => setNext(e.target.value)} /></div>
      <div className="md:col-span-3 flex items-end justify-end">
        <button className="ec-btn-primary" disabled={!title || !amount || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save'}</button>
      </div>
    </div>
  );
}
