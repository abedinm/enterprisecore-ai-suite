import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { CheckCircle2, Circle, CircleDollarSign, Flag, Plus, Trash2, X } from 'lucide-react';
import {
  constructionApi,
  formatMoney,
  shortDate,
  type Milestone,
  type MilestoneInput,
} from '../../lib/construction';

const EMPTY: MilestoneInput = {
  name: '',
  planned_date: new Date().toISOString().slice(0, 10),
  actual_date: null,
  status: 'pending',
  payment_trigger: false,
  payment_amount: null,
  notes: '',
};

function isComplete(m: Milestone): boolean {
  return !!m.actual_date || m.status.toLowerCase().includes('complete');
}

export function ConstructionMilestonesPage() {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['construction', 'milestones', projectId],
    queryFn: () => constructionApi.listMilestones(projectId),
    enabled: !!projectId,
  });

  const [editing, setEditing] = useState<Milestone | null>(null);
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => constructionApi.deleteMilestone(projectId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'milestones', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'dashboard', projectId] });
      toast.success('Milestone removed');
    },
  });

  const sorted = (listQ.data ?? []).slice().sort(
    (a, b) => new Date(a.planned_date).getTime() - new Date(b.planned_date).getTime(),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Flag size={18} className="text-brand-600" /> Milestones
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Key delivery dates and payment triggers along the project timeline.
          </p>
        </div>
        <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
          <Plus size={14} /> New milestone
        </button>
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}

      {listQ.data && listQ.data.length === 0 && (
        <div className="ec-card flex flex-col items-start gap-3 p-6">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
            <Flag size={22} />
          </div>
          <div>
            <h3 className="font-semibold">No milestones yet</h3>
            <p className="mt-1 text-sm text-ink-muted">
              Plot your first milestone to start building the project timeline.
            </p>
          </div>
          <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
            <Plus size={14} /> Create first milestone
          </button>
        </div>
      )}

      {sorted.length > 0 && (
        <div className="ec-card p-5">
          <ol className="relative space-y-4 border-l-2 border-border pl-6">
            {sorted.map((m) => {
              const done = isComplete(m);
              return (
                <li key={m.id} className="relative">
                  <span
                    className={`absolute -left-[33px] grid h-6 w-6 place-items-center rounded-full border-2 ${done ? 'border-emerald-500 bg-emerald-500 text-white' : 'border-brand-600 bg-surface-elevated text-brand-600'}`}
                  >
                    {done ? <CheckCircle2 size={14} /> : <Circle size={12} />}
                  </span>
                  <button
                    type="button"
                    className="ec-card flex w-full flex-wrap items-start justify-between gap-3 p-3 text-left hover:border-brand-500/40 hover:bg-surface-muted/30"
                    onClick={() => setEditing(m)}
                  >
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-semibold">{m.name}</p>
                        <span className={done ? 'ec-badge-green' : 'ec-badge-blue'}>{m.status}</span>
                        {m.payment_trigger && (
                          <span className="ec-badge-amber inline-flex items-center gap-1">
                            <CircleDollarSign size={11} />
                            {m.payment_amount ? formatMoney(m.payment_amount) : 'Payment'}
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-xs text-ink-muted">
                        Planned {shortDate(m.planned_date)}
                        {m.actual_date && ` · Actual ${shortDate(m.actual_date)}`}
                      </p>
                      {m.notes && (
                        <p className="mt-1 line-clamp-2 text-xs text-ink-muted">{m.notes}</p>
                      )}
                    </div>
                    <button
                      type="button"
                      className="ec-btn-ghost !px-1.5 !py-1 text-rose-600"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm(`Delete milestone "${m.name}"?`)) remove.mutate(m.id);
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </button>
                </li>
              );
            })}
          </ol>
        </div>
      )}

      {(editing || creating) && (
        <MilestoneModal
          projectId={projectId}
          milestone={editing}
          isNew={creating}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

function MilestoneModal({
  projectId,
  milestone,
  isNew,
  onClose,
}: {
  projectId: string;
  milestone: Milestone | null;
  isNew: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<MilestoneInput>(
    milestone
      ? {
          name: milestone.name,
          planned_date: milestone.planned_date,
          actual_date: milestone.actual_date,
          status: milestone.status,
          payment_trigger: milestone.payment_trigger,
          payment_amount: milestone.payment_amount,
          notes: milestone.notes ?? '',
        }
      : EMPTY,
  );

  const update = <K extends keyof MilestoneInput>(key: K, value: MilestoneInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const save = useMutation({
    mutationFn: () => {
      if (isNew) return constructionApi.createMilestone(projectId, form);
      if (!milestone) throw new Error('No milestone');
      return constructionApi.updateMilestone(projectId, milestone.id, form);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'milestones', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'dashboard', projectId] });
      toast.success(isNew ? 'Milestone created' : 'Milestone saved');
      onClose();
    },
  });

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold">{isNew ? 'New milestone' : 'Edit milestone'}</p>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}><X size={16} /></button>
        </div>
        <form
          className="max-h-[70vh] space-y-3 overflow-y-auto p-5"
          onSubmit={(e) => { e.preventDefault(); save.mutate(); }}
        >
          <div>
            <label className="ec-label">Name</label>
            <input required className="ec-input" value={form.name} onChange={(e) => update('name', e.target.value)} />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="ec-label">Planned date</label>
              <input type="date" className="ec-input" value={form.planned_date}
                onChange={(e) => update('planned_date', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Actual date</label>
              <input type="date" className="ec-input" value={form.actual_date ?? ''}
                onChange={(e) => update('actual_date', e.target.value || null)} />
            </div>
            <div>
              <label className="ec-label">Status</label>
              <input className="ec-input" value={form.status} onChange={(e) => update('status', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Payment amount</label>
              <input className="ec-input" inputMode="decimal" value={form.payment_amount ?? ''}
                onChange={(e) => update('payment_amount', e.target.value || null)} />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.payment_trigger}
              onChange={(e) => update('payment_trigger', e.target.checked)}
            />
            Triggers a payment when complete
          </label>
          <div>
            <label className="ec-label">Notes</label>
            <textarea className="ec-input min-h-[60px]" value={form.notes ?? ''}
              onChange={(e) => update('notes', e.target.value)} />
          </div>
        </form>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="ec-btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? 'Saving…' : isNew ? 'Create' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
