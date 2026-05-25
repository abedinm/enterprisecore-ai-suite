import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { AlertTriangle, Award, Gauge, Plus, Trash2, Wallet, X } from 'lucide-react';
import {
  academicApi,
  academicDeepApi,
  type BudgetStatus,
  type FinanceRecordInput,
  type FinanceSummary,
  type ScholarshipInput,
  type StudentBudget,
} from '../../lib/academic';
import { useAuthStore } from '../../store/auth';
import { isAcademicAdmin } from '../../lib/academicRoles';

const EMPTY_RECORD: FinanceRecordInput = {
  student_id: null,
  kind: 'fee',
  amount: 0,
  currency: 'USD',
  due_date: '',
  status: 'pending',
  notes: '',
};

const EMPTY_SCH: ScholarshipInput = {
  name: '',
  description: '',
  amount: 0,
  currency: 'USD',
  deadline: '',
};

export function AcademicFinancePage() {
  const user = useAuthStore((s) => s.user);
  const canManage = isAcademicAdmin(user?.role);

  return (
    <div className="space-y-6">
      {!canManage && <MySummaryCard />}
      {!canManage && <BudgetSection />}
      <RecordsSection canManage={canManage} />
      <ScholarshipsSection canManage={canManage} />
    </div>
  );
}

function MySummaryCard() {
  const q = useQuery({
    queryKey: ['academic', 'finance', 'my-summary'],
    queryFn: () => academicDeepApi.myFinanceSummary(),
  });
  if (q.isLoading) return null;
  const s = q.data as FinanceSummary | undefined;
  if (!s) return null;
  return (
    <section className="ec-card grid gap-3 p-4 sm:grid-cols-4">
      <Stat label="Income" value={`${s.currency} ${s.total_allowance}`} />
      <Stat label="Expense" value={`${s.currency} ${s.total_expense}`} />
      <Stat
        label="Net"
        value={`${s.currency} ${s.net}`}
        accent={parseFloat(s.net) >= 0 ? 'text-emerald-600' : 'text-rose-600'}
      />
      <Stat
        label="Saved"
        value={`${Math.round((s.savings_rate || 0) * 100)}%`}
      />
    </section>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div>
      <p className="text-xs uppercase text-ink-muted">{label}</p>
      <p className={`text-lg font-semibold ${accent ?? ''}`}>{value}</p>
    </div>
  );
}

function BudgetSection() {
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['academic', 'finance', 'budgets'],
    queryFn: () => academicDeepApi.listBudgets(),
  });
  const statusQ = useQuery({
    queryKey: ['academic', 'finance', 'budget-status'],
    queryFn: () => academicDeepApi.myBudgetStatus(),
  });
  const [cat, setCat] = useState('');
  const [limit, setLimit] = useState('');
  const create = useMutation({
    mutationFn: () =>
      academicDeepApi.createBudget({
        category: cat,
        monthly_limit: limit,
        currency: 'USD',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'finance', 'budgets'] });
      qc.invalidateQueries({
        queryKey: ['academic', 'finance', 'budget-status'],
      });
      setCat('');
      setLimit('');
      toast.success('Budget added');
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Failed');
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => academicDeepApi.deleteBudget(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'finance', 'budgets'] });
      qc.invalidateQueries({
        queryKey: ['academic', 'finance', 'budget-status'],
      });
      toast.success('Budget removed');
    },
  });
  const status = statusQ.data as BudgetStatus | undefined;
  const budgets = (listQ.data ?? []) as StudentBudget[];
  return (
    <section className="ec-card p-4">
      <p className="mb-3 inline-flex items-center gap-2 font-semibold">
        <Gauge size={14} className="text-brand-600" />
        Monthly budgets
      </p>
      {status && status.rows.length > 0 && (
        <ul className="mb-3 space-y-1 text-sm">
          {status.rows.map((row) => (
            <li
              key={row.category}
              className={
                row.over_budget
                  ? 'flex items-center gap-2 text-rose-600'
                  : 'flex items-center gap-2 text-ink'
              }
            >
              {row.over_budget && <AlertTriangle size={12} />}
              <span className="font-medium">{row.category}</span>
              <span className="text-ink-muted">
                spent {row.spent} / {row.monthly_limit}
                {row.over_budget && <> · over by {row.over_by}</>}
              </span>
            </li>
          ))}
        </ul>
      )}
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <div className="flex-1 min-w-[120px]">
          <label className="ec-label">Category</label>
          <input
            required
            className="ec-input"
            value={cat}
            onChange={(e) => setCat(e.target.value)}
            placeholder="food"
          />
        </div>
        <div className="flex-1 min-w-[100px]">
          <label className="ec-label">Monthly limit</label>
          <input
            required
            type="number"
            step="0.01"
            min={0}
            className="ec-input"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
            placeholder="100"
          />
        </div>
        <button
          type="submit"
          className="ec-btn-primary"
          disabled={create.isPending || !cat.trim() || !limit}
        >
          {create.isPending ? 'Saving…' : 'Add budget'}
        </button>
      </form>
      {budgets.length > 0 && (
        <ul className="mt-3 grid gap-1 text-xs sm:grid-cols-2">
          {budgets.map((b) => (
            <li
              key={b.id}
              className="flex items-center justify-between rounded border border-border/60 px-2 py-1"
            >
              <span>
                {b.category}: {b.currency} {b.monthly_limit}
              </span>
              <button
                type="button"
                className="text-rose-600"
                onClick={() => remove.mutate(b.id)}
              >
                <Trash2 size={11} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function RecordsSection({ canManage }: { canManage: boolean }) {
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['academic', 'finance-records'],
    queryFn: () => academicApi.listFinanceRecords(),
  });
  const [creating, setCreating] = useState(false);
  const remove = useMutation({
    mutationFn: (id: string) => academicApi.deleteFinanceRecord(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'finance-records'] });
      toast.success('Record removed');
    },
  });

  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold inline-flex items-center gap-2">
            <Wallet size={18} className="text-brand-600" /> Records
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Tuition, fees, payments, financial aid. Students see only their own;
            admins/managers see everyone.
          </p>
        </div>
        {canManage && (
          <button
            type="button"
            className="ec-btn-primary"
            onClick={() => setCreating(true)}
          >
            <Plus size={14} /> New record
          </button>
        )}
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted mt-3">Loading…</p>}
      {listQ.data && listQ.data.length === 0 && (
        <p className="ec-card p-6 text-center text-sm text-ink-muted mt-3">
          No records yet.
        </p>
      )}
      {listQ.data && listQ.data.length > 0 && (
        <div className="ec-card mt-3 overflow-x-auto">
          <table className="ec-table">
            <thead>
              <tr>
                <th>Student</th>
                <th>Kind</th>
                <th className="text-right">Amount</th>
                <th>Due</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {listQ.data.map((r) => (
                <tr key={r.id}>
                  <td>{r.student_name ?? r.student_id ?? '—'}</td>
                  <td>
                    <span className="ec-badge bg-surface-muted text-ink-muted">
                      {r.kind}
                    </span>
                  </td>
                  <td className="text-right font-mono">
                    {(r.currency ?? '$') + ' ' + Number(r.amount).toFixed(2)}
                  </td>
                  <td className="text-ink-muted">{r.due_date ?? '—'}</td>
                  <td>
                    <span
                      className={
                        r.status === 'paid'
                          ? 'ec-badge-green'
                          : r.status === 'overdue'
                          ? 'ec-badge-rose'
                          : 'ec-badge-amber'
                      }
                    >
                      {r.status ?? '—'}
                    </span>
                  </td>
                  <td className="text-right">
                    {canManage && (
                      <button
                        type="button"
                        className="ec-btn-ghost !px-2 !py-1 text-rose-600"
                        onClick={() => {
                          if (confirm('Delete this record?')) remove.mutate(r.id);
                        }}
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {creating && <RecordModal onClose={() => setCreating(false)} />}
    </section>
  );
}

function RecordModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<FinanceRecordInput>(EMPTY_RECORD);
  const save = useMutation({
    mutationFn: () => academicApi.createFinanceRecord(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'finance-records'] });
      toast.success('Record created');
      onClose();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Failed to save');
    },
  });
  return (
    <Modal title="New record" onClose={onClose}>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="ec-label">Kind</label>
            <select
              className="ec-input"
              value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value })}
            >
              <option value="fee">Fee</option>
              <option value="payment">Payment</option>
              <option value="aid">Aid</option>
            </select>
          </div>
          <div>
            <label className="ec-label">Status</label>
            <select
              className="ec-input"
              value={form.status ?? 'pending'}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
            >
              <option value="pending">Pending</option>
              <option value="paid">Paid</option>
              <option value="overdue">Overdue</option>
            </select>
          </div>
          <div>
            <label className="ec-label">Amount</label>
            <input
              type="number"
              step="0.01"
              required
              className="ec-input"
              value={form.amount}
              onChange={(e) =>
                setForm({ ...form, amount: parseFloat(e.target.value) || 0 })
              }
            />
          </div>
          <div>
            <label className="ec-label">Currency</label>
            <input
              className="ec-input"
              value={form.currency ?? 'USD'}
              onChange={(e) => setForm({ ...form, currency: e.target.value })}
            />
          </div>
          <div className="sm:col-span-2">
            <label className="ec-label">Due date</label>
            <input
              type="date"
              className="ec-input"
              value={form.due_date ?? ''}
              onChange={(e) => setForm({ ...form, due_date: e.target.value })}
            />
          </div>
          <div className="sm:col-span-2">
            <label className="ec-label">Notes</label>
            <textarea
              className="ec-input min-h-[60px]"
              value={form.notes ?? ''}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            className="ec-btn-primary"
            disabled={save.isPending}
          >
            {save.isPending ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ScholarshipsSection({ canManage }: { canManage: boolean }) {
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['academic', 'scholarships'],
    queryFn: () => academicApi.listScholarships(),
  });
  const [creating, setCreating] = useState(false);
  const remove = useMutation({
    mutationFn: (id: string) => academicApi.deleteScholarship(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'scholarships'] });
      toast.success('Scholarship removed');
    },
  });

  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold inline-flex items-center gap-2">
            <Award size={18} className="text-brand-600" /> Scholarships
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Catalogue of scholarships available to students.
          </p>
        </div>
        {canManage && (
          <button
            type="button"
            className="ec-btn-primary"
            onClick={() => setCreating(true)}
          >
            <Plus size={14} /> Add scholarship
          </button>
        )}
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted mt-3">Loading…</p>}
      {listQ.data && listQ.data.length === 0 && (
        <p className="ec-card p-6 text-center text-sm text-ink-muted mt-3">
          No scholarships listed yet.
        </p>
      )}
      {listQ.data && listQ.data.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 mt-3">
          {listQ.data.map((s) => (
            <article key={s.id} className="ec-card flex flex-col gap-2 p-4">
              <div className="flex items-start justify-between">
                <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-600/10 text-brand-600">
                  <Award size={16} />
                </span>
                {s.deadline && (
                  <span className="ec-badge bg-surface-muted text-ink-muted">
                    by {s.deadline}
                  </span>
                )}
              </div>
              <p className="font-semibold">{s.name}</p>
              {s.description && (
                <p className="line-clamp-2 text-xs text-ink-muted">
                  {s.description}
                </p>
              )}
              <p className="font-mono text-sm">
                {s.currency ?? '$'} {Number(s.amount).toFixed(2)}
              </p>
              <div className="mt-auto flex justify-end pt-2">
                {canManage && (
                  <button
                    type="button"
                    className="ec-btn-ghost !px-2 !py-1 text-rose-600"
                    onClick={() => {
                      if (confirm(`Delete "${s.name}"?`)) remove.mutate(s.id);
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      {creating && <ScholarshipModal onClose={() => setCreating(false)} />}
    </section>
  );
}

function ScholarshipModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<ScholarshipInput>(EMPTY_SCH);
  const save = useMutation({
    mutationFn: () => academicApi.createScholarship(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'scholarships'] });
      toast.success('Scholarship added');
      onClose();
    },
  });
  return (
    <Modal title="Add scholarship" onClose={onClose}>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div>
          <label className="ec-label">Name</label>
          <input
            required
            className="ec-input"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="ec-label">Amount</label>
            <input
              type="number"
              step="0.01"
              className="ec-input"
              value={form.amount}
              onChange={(e) =>
                setForm({ ...form, amount: parseFloat(e.target.value) || 0 })
              }
            />
          </div>
          <div>
            <label className="ec-label">Currency</label>
            <input
              className="ec-input"
              value={form.currency ?? 'USD'}
              onChange={(e) => setForm({ ...form, currency: e.target.value })}
            />
          </div>
        </div>
        <div>
          <label className="ec-label">Deadline</label>
          <input
            type="date"
            className="ec-input"
            value={form.deadline ?? ''}
            onChange={(e) => setForm({ ...form, deadline: e.target.value })}
          />
        </div>
        <div>
          <label className="ec-label">Description</label>
          <textarea
            className="ec-input min-h-[80px]"
            value={form.description ?? ''}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            className="ec-btn-primary"
            disabled={save.isPending || !form.name.trim()}
          >
            {save.isPending ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold">{title}</p>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}
