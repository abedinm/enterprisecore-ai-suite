import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/utils';

type Expense = {
  id: string; category_id: string | null; vendor_id: string | null;
  date: string; amount: string; currency: string; description: string;
};
type Category = { id: string; name: string };

export function ExpensesTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const { data: expenses } = useQuery({
    queryKey: ['finance', 'expenses'],
    queryFn: async () => (await api.get<Expense[]>('/finance/expenses')).data,
  });
  const { data: cats } = useQuery({
    queryKey: ['finance', 'expense-categories'],
    queryFn: async () => (await api.get<Category[]>('/finance/expense-categories')).data,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/finance/expenses/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['finance', 'expenses'] }),
  });

  const total = (expenses ?? []).reduce((sum, e) => sum + parseFloat(e.amount), 0);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-muted">{expenses?.length ?? 0} expenses • Total {formatCurrency(total)}</p>
        <button className="ec-btn-primary" onClick={() => setShow((v) => !v)}><Plus size={16} /> {show ? 'Close' : 'New expense'}</button>
      </div>
      {show && cats && <ExpenseForm categories={cats} onSaved={() => { setShow(false); qc.invalidateQueries({ queryKey: ['finance', 'expenses'] }); }} />}
      <div className="overflow-x-auto">
        <table className="ec-table">
          <thead><tr><th>Date</th><th>Description</th><th>Category</th><th>Amount</th><th></th></tr></thead>
          <tbody>
            {expenses?.length ? expenses.map((e) => (
              <tr key={e.id}>
                <td>{formatDate(e.date)}</td>
                <td>{e.description}</td>
                <td>{cats?.find((c) => c.id === e.category_id)?.name ?? '—'}</td>
                <td>{formatCurrency(e.amount, e.currency)}</td>
                <td className="text-right">
                  <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete this expense?')) remove.mutate(e.id); }}><Trash2 size={16} /></button>
                </td>
              </tr>
            )) : <tr><td colSpan={5} className="py-8 text-center text-ink-muted">No expenses recorded.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ExpenseForm({ categories, onSaved }: { categories: Category[]; onSaved: () => void }) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [amount, setAmount] = useState(0);
  const [currency, setCurrency] = useState('USD');
  const [description, setDescription] = useState('');
  const [categoryId, setCategoryId] = useState(categories[0]?.id ?? '');
  const save = useMutation({
    mutationFn: async () => (await api.post('/finance/expenses', {
      date, amount, currency, description, category_id: categoryId || null,
    })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 grid gap-3 md:grid-cols-5">
      <div><label className="ec-label">Date</label><input type="date" className="ec-input" value={date} onChange={(e) => setDate(e.target.value)} /></div>
      <div><label className="ec-label">Amount</label><input type="number" step="any" className="ec-input" value={amount} onChange={(e) => setAmount(Number(e.target.value))} /></div>
      <div><label className="ec-label">Currency</label><input className="ec-input" maxLength={3} value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} /></div>
      <div className="md:col-span-2"><label className="ec-label">Description</label><input className="ec-input" value={description} onChange={(e) => setDescription(e.target.value)} /></div>
      <div className="md:col-span-2"><label className="ec-label">Category</label>
        <select className="ec-input" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">—</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>
      <div className="md:col-span-3 flex items-end justify-end">
        <button className="ec-btn-primary" disabled={!amount || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save expense'}</button>
      </div>
    </div>
  );
}
