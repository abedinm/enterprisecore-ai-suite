import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { AlertTriangle, Plus, Shield, Trash2, X } from 'lucide-react';
import {
  constructionApi,
  daysUntil,
  formatMoney,
  INSURANCE_TYPE_OPTIONS,
  shortDate,
  type Insurance,
  type InsuranceInput,
  type InsuranceType,
} from '../../lib/construction';

const EMPTY: InsuranceInput = {
  insurance_type: 'CAR',
  provider: '',
  policy_number: '',
  sum_insured: '0',
  currency: 'USD',
  start_date: new Date().toISOString().slice(0, 10),
  expiry_date: new Date(Date.now() + 365 * 86_400_000).toISOString().slice(0, 10),
  premium_amount: null,
  renewal_reminder_days: 30,
};

function expiryBadgeClass(expiry: string, reminderDays: number): string {
  const days = daysUntil(expiry);
  if (days === null) return 'ec-badge bg-surface-muted text-ink-muted';
  if (days < 0) return 'ec-badge-rose';
  if (days <= reminderDays) return 'ec-badge-amber';
  return 'ec-badge-green';
}

export function ConstructionInsurancesPage() {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['construction', 'insurances', projectId],
    queryFn: () => constructionApi.listInsurances(projectId),
    enabled: !!projectId,
  });

  const [editing, setEditing] = useState<Insurance | null>(null);
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => constructionApi.deleteInsurance(projectId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'insurances', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'dashboard', projectId] });
      toast.success('Policy removed');
    },
  });

  const sorted = (listQ.data ?? []).slice().sort((a, b) => {
    return new Date(a.expiry_date).getTime() - new Date(b.expiry_date).getTime();
  });

  const expiringSoon = sorted.filter((p) => {
    const d = daysUntil(p.expiry_date);
    return d !== null && d >= 0 && d <= p.renewal_reminder_days;
  });
  const expired = sorted.filter((p) => {
    const d = daysUntil(p.expiry_date);
    return d !== null && d < 0;
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Shield size={18} className="text-brand-600" /> Insurances
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Project policies including CAR, PI, PL, EL, and marine cargo coverage.
          </p>
        </div>
        <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
          <Plus size={14} /> New policy
        </button>
      </div>

      {(expiringSoon.length > 0 || expired.length > 0) && (
        <div className="ec-card border-amber-300 bg-amber-50 p-3 text-sm dark:bg-amber-900/20">
          <p className="flex items-center gap-2 font-semibold text-amber-700 dark:text-amber-300">
            <AlertTriangle size={14} />
            {expired.length > 0 && `${expired.length} expired`}
            {expired.length > 0 && expiringSoon.length > 0 && ' · '}
            {expiringSoon.length > 0 && `${expiringSoon.length} expiring within reminder window`}
          </p>
        </div>
      )}

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}

      {sorted.length === 0 && !listQ.isLoading && (
        <div className="ec-card flex flex-col items-start gap-3 p-6">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
            <Shield size={22} />
          </div>
          <div>
            <h3 className="font-semibold">No insurance policies logged</h3>
            <p className="mt-1 text-sm text-ink-muted">
              Add the project's CAR / PI / PL policies so the dashboard can warn before expiry.
            </p>
          </div>
          <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
            <Plus size={14} /> Add first policy
          </button>
        </div>
      )}

      {sorted.length > 0 && (
        <div className="ec-card overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-surface-muted/40 text-left text-xs uppercase tracking-wider text-ink-subtle">
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Provider</th>
                <th className="px-3 py-2">Policy #</th>
                <th className="px-3 py-2 text-right">Sum insured</th>
                <th className="px-3 py-2">Start</th>
                <th className="px-3 py-2">Expiry</th>
                <th className="px-3 py-2 text-right">Premium</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((p) => {
                const days = daysUntil(p.expiry_date);
                const rowClass = days !== null && days < 0
                  ? 'bg-rose-50/40 dark:bg-rose-900/10'
                  : days !== null && days <= p.renewal_reminder_days
                    ? 'bg-amber-50/30 dark:bg-amber-900/10'
                    : '';
                return (
                  <tr
                    key={p.id}
                    className={`cursor-pointer border-b border-border/60 last:border-b-0 hover:bg-surface-muted/30 ${rowClass}`}
                    onClick={() => setEditing(p)}
                  >
                    <td className="px-3 py-2">
                      <span className="ec-badge bg-surface-muted text-ink-muted">{p.insurance_type}</span>
                    </td>
                    <td className="px-3 py-2 font-medium">{p.provider}</td>
                    <td className="px-3 py-2 font-mono text-xs text-ink-muted">{p.policy_number}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatMoney(p.sum_insured, p.currency)}</td>
                    <td className="px-3 py-2 text-ink-muted">{shortDate(p.start_date)}</td>
                    <td className="px-3 py-2">
                      <span className={expiryBadgeClass(p.expiry_date, p.renewal_reminder_days)}>
                        {shortDate(p.expiry_date)}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-ink-muted">
                      {p.premium_amount ? formatMoney(p.premium_amount, p.currency) : '—'}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        type="button"
                        className="ec-btn-ghost !px-1.5 !py-1 text-rose-600"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm(`Delete policy ${p.policy_number}?`)) remove.mutate(p.id);
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
        <InsuranceModal
          projectId={projectId}
          insurance={editing}
          isNew={creating}
          onClose={() => { setCreating(false); setEditing(null); }}
        />
      )}
    </div>
  );
}

function InsuranceModal({
  projectId,
  insurance,
  isNew,
  onClose,
}: {
  projectId: string;
  insurance: Insurance | null;
  isNew: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<InsuranceInput>(
    insurance
      ? {
          insurance_type: insurance.insurance_type,
          provider: insurance.provider,
          policy_number: insurance.policy_number,
          sum_insured: insurance.sum_insured,
          currency: insurance.currency,
          start_date: insurance.start_date,
          expiry_date: insurance.expiry_date,
          premium_amount: insurance.premium_amount,
          renewal_reminder_days: insurance.renewal_reminder_days,
        }
      : EMPTY,
  );

  const update = <K extends keyof InsuranceInput>(key: K, value: InsuranceInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const save = useMutation({
    mutationFn: () => {
      if (isNew) return constructionApi.createInsurance(projectId, form);
      if (!insurance) throw new Error('No insurance');
      return constructionApi.updateInsurance(projectId, insurance.id, form);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'insurances', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'dashboard', projectId] });
      toast.success(isNew ? 'Policy added' : 'Policy saved');
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
          <p className="font-semibold">{isNew ? 'New insurance policy' : 'Edit policy'}</p>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}><X size={16} /></button>
        </div>
        <form
          className="max-h-[70vh] space-y-3 overflow-y-auto p-5"
          onSubmit={(e) => { e.preventDefault(); save.mutate(); }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="ec-label">Type</label>
              <select
                className="ec-input"
                value={form.insurance_type}
                onChange={(e) => update('insurance_type', e.target.value as InsuranceType)}
              >
                {INSURANCE_TYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="ec-label">Provider</label>
              <input required className="ec-input" value={form.provider}
                onChange={(e) => update('provider', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Policy number</label>
              <input required className="ec-input" value={form.policy_number}
                onChange={(e) => update('policy_number', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Renewal reminder (days)</label>
              <input type="number" min={0} className="ec-input" value={form.renewal_reminder_days}
                onChange={(e) => update('renewal_reminder_days', Math.max(0, Number(e.target.value) || 0))} />
            </div>
            <div>
              <label className="ec-label">Sum insured</label>
              <input className="ec-input" inputMode="decimal" value={form.sum_insured}
                onChange={(e) => update('sum_insured', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Currency</label>
              <input className="ec-input" maxLength={3} value={form.currency}
                onChange={(e) => update('currency', e.target.value.toUpperCase())} />
            </div>
            <div>
              <label className="ec-label">Start</label>
              <input type="date" className="ec-input" value={form.start_date}
                onChange={(e) => update('start_date', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Expiry</label>
              <input type="date" className="ec-input" value={form.expiry_date}
                onChange={(e) => update('expiry_date', e.target.value)} />
            </div>
            <div className="md:col-span-2">
              <label className="ec-label">Premium amount</label>
              <input className="ec-input" inputMode="decimal" value={form.premium_amount ?? ''}
                onChange={(e) => update('premium_amount', e.target.value || null)} />
            </div>
          </div>
        </form>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="ec-btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? 'Saving…' : isNew ? 'Add policy' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
