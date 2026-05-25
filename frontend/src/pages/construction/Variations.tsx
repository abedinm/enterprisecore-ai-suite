import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ClipboardSignature, Plus, Trash2, TrendingDown, TrendingUp, X } from 'lucide-react';
import {
  constructionApi,
  formatMoney,
  shortDate,
  type Variation,
  type VariationInput,
} from '../../lib/construction';

const EMPTY: VariationInput = {
  title: '',
  description: '',
  requested_by: '',
  cost_impact: '0',
  time_impact_days: 0,
  status: 'submitted',
  justification: '',
  submitted_at: new Date().toISOString().slice(0, 10),
  decided_at: null,
};

function statusBadge(status: string): string {
  const s = status.toLowerCase();
  if (s.includes('approve')) return 'ec-badge-green';
  if (s.includes('reject')) return 'ec-badge-rose';
  if (s.includes('review') || s.includes('pending') || s.includes('submit')) return 'ec-badge-amber';
  return 'ec-badge-blue';
}

export function ConstructionVariationsPage() {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['construction', 'variations', projectId],
    queryFn: () => constructionApi.listVariations(projectId),
    enabled: !!projectId,
  });
  const [editing, setEditing] = useState<Variation | null>(null);
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => constructionApi.deleteVariation(projectId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'variations', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'dashboard', projectId] });
      toast.success('Variation removed');
    },
  });

  const totals = useMemo(() => {
    let approvedCost = 0;
    let approvedDays = 0;
    let pendingCost = 0;
    for (const v of listQ.data ?? []) {
      const cost = Number(v.cost_impact) || 0;
      const days = v.time_impact_days || 0;
      if (v.status.toLowerCase().includes('approve')) {
        approvedCost += cost;
        approvedDays += days;
      } else if (!v.status.toLowerCase().includes('reject')) {
        pendingCost += cost;
      }
    }
    return { approvedCost, approvedDays, pendingCost };
  }, [listQ.data]);

  const sorted = (listQ.data ?? []).slice().sort(
    (a, b) => new Date(b.submitted_at).getTime() - new Date(a.submitted_at).getTime(),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <ClipboardSignature size={18} className="text-brand-600" /> Variations
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Change requests with cost and time impact. Approved totals are running.
          </p>
        </div>
        <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
          <Plus size={14} /> New variation
        </button>
      </div>

      {/* Running totals */}
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="ec-card p-4">
          <p className="text-xs uppercase tracking-wider text-ink-subtle">Approved cost impact</p>
          <p className={`mt-1 flex items-center gap-1 text-xl font-semibold ${totals.approvedCost > 0 ? 'text-rose-600' : totals.approvedCost < 0 ? 'text-emerald-600' : ''}`}>
            {totals.approvedCost > 0 ? <TrendingUp size={16} /> : totals.approvedCost < 0 ? <TrendingDown size={16} /> : null}
            {totals.approvedCost > 0 ? '+' : ''}{formatMoney(String(totals.approvedCost))}
          </p>
        </div>
        <div className="ec-card p-4">
          <p className="text-xs uppercase tracking-wider text-ink-subtle">Approved time impact</p>
          <p className="mt-1 text-xl font-semibold">{totals.approvedDays} days</p>
        </div>
        <div className="ec-card p-4">
          <p className="text-xs uppercase tracking-wider text-ink-subtle">Pending cost impact</p>
          <p className="mt-1 text-xl font-semibold text-amber-600">
            {totals.pendingCost > 0 ? '+' : ''}{formatMoney(String(totals.pendingCost))}
          </p>
        </div>
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}

      {sorted.length === 0 && !listQ.isLoading && (
        <div className="ec-card flex flex-col items-start gap-3 p-6">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
            <ClipboardSignature size={22} />
          </div>
          <div>
            <h3 className="font-semibold">No variations submitted</h3>
            <p className="mt-1 text-sm text-ink-muted">
              Log changes that affect cost or schedule to keep the contract value reconciled.
            </p>
          </div>
          <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
            <Plus size={14} /> Add first variation
          </button>
        </div>
      )}

      {sorted.length > 0 && (
        <div className="ec-card overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-surface-muted/40 text-left text-xs uppercase tracking-wider text-ink-subtle">
                <th className="px-3 py-2">#</th>
                <th className="px-3 py-2">Title</th>
                <th className="px-3 py-2">Requested by</th>
                <th className="px-3 py-2 text-right">Cost impact</th>
                <th className="px-3 py-2 text-right">Time</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Submitted</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((v) => {
                const cost = Number(v.cost_impact) || 0;
                return (
                  <tr
                    key={v.id}
                    className="cursor-pointer border-b border-border/60 last:border-b-0 hover:bg-surface-muted/30"
                    onClick={() => setEditing(v)}
                  >
                    <td className="px-3 py-2 font-mono text-xs text-ink-muted">{v.number}</td>
                    <td className="px-3 py-2 font-medium">{v.title}</td>
                    <td className="px-3 py-2 text-ink-muted">{v.requested_by}</td>
                    <td className={`px-3 py-2 text-right font-mono ${cost > 0 ? 'text-rose-600' : cost < 0 ? 'text-emerald-600' : 'text-ink-muted'}`}>
                      {cost > 0 ? '+' : ''}{formatMoney(v.cost_impact)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-ink-muted">{v.time_impact_days}d</td>
                    <td className="px-3 py-2"><span className={statusBadge(v.status)}>{v.status}</span></td>
                    <td className="px-3 py-2 text-ink-muted">{shortDate(v.submitted_at)}</td>
                    <td className="px-3 py-2 text-right">
                      <button
                        type="button"
                        className="ec-btn-ghost !px-1.5 !py-1 text-rose-600"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm(`Delete ${v.number}?`)) remove.mutate(v.id);
                        }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {(editing || creating) && (
        <VariationModal
          projectId={projectId}
          variation={editing}
          isNew={creating}
          onClose={() => { setCreating(false); setEditing(null); }}
        />
      )}
    </div>
  );
}

function VariationModal({
  projectId,
  variation,
  isNew,
  onClose,
}: {
  projectId: string;
  variation: Variation | null;
  isNew: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<VariationInput>(
    variation
      ? {
          title: variation.title,
          description: variation.description,
          requested_by: variation.requested_by,
          cost_impact: variation.cost_impact,
          time_impact_days: variation.time_impact_days,
          status: variation.status,
          justification: variation.justification ?? '',
          submitted_at: variation.submitted_at,
          decided_at: variation.decided_at,
        }
      : EMPTY,
  );

  const update = <K extends keyof VariationInput>(key: K, value: VariationInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const save = useMutation({
    mutationFn: () => {
      if (isNew) return constructionApi.createVariation(projectId, form);
      if (!variation) throw new Error('No variation');
      return constructionApi.updateVariation(projectId, variation.id, form);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'variations', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'dashboard', projectId] });
      toast.success(isNew ? 'Variation submitted' : 'Variation saved');
      onClose();
    },
  });

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-2xl overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold">{isNew ? 'New variation' : `Edit ${variation?.number ?? ''}`}</p>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}><X size={16} /></button>
        </div>
        <form
          className="max-h-[70vh] space-y-3 overflow-y-auto p-5"
          onSubmit={(e) => { e.preventDefault(); save.mutate(); }}
        >
          <div>
            <label className="ec-label">Title</label>
            <input required className="ec-input" value={form.title}
              onChange={(e) => update('title', e.target.value)} />
          </div>
          <div>
            <label className="ec-label">Description</label>
            <textarea required className="ec-input min-h-[80px]" value={form.description}
              onChange={(e) => update('description', e.target.value)} />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="ec-label">Requested by</label>
              <input required className="ec-input" value={form.requested_by}
                onChange={(e) => update('requested_by', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Status</label>
              <input className="ec-input" value={form.status}
                onChange={(e) => update('status', e.target.value)}
                placeholder="submitted / review / approved / rejected" />
            </div>
            <div>
              <label className="ec-label">Cost impact (+/-)</label>
              <input className="ec-input" inputMode="decimal" value={form.cost_impact}
                onChange={(e) => update('cost_impact', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Time impact (days)</label>
              <input type="number" className="ec-input" value={form.time_impact_days}
                onChange={(e) => update('time_impact_days', Number(e.target.value) || 0)} />
            </div>
            <div>
              <label className="ec-label">Submitted at</label>
              <input type="date" className="ec-input" value={form.submitted_at}
                onChange={(e) => update('submitted_at', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Decided at</label>
              <input type="date" className="ec-input" value={form.decided_at ?? ''}
                onChange={(e) => update('decided_at', e.target.value || null)} />
            </div>
          </div>
          <div>
            <label className="ec-label">Justification</label>
            <textarea className="ec-input min-h-[80px]" value={form.justification ?? ''}
              onChange={(e) => update('justification', e.target.value)} />
          </div>
        </form>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="ec-btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? 'Saving…' : isNew ? 'Submit' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
