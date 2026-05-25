import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { AlertTriangle, FileText, Plus, Trash2, X } from 'lucide-react';
import {
  constructionApi,
  daysUntil,
  shortDate,
  type Permit,
  type PermitInput,
} from '../../lib/construction';

const EMPTY: PermitInput = {
  permit_type: '',
  issuing_authority: '',
  application_date: new Date().toISOString().slice(0, 10),
  approval_date: null,
  expiry_date: null,
  status: 'pending',
  reference_number: '',
  conditions: '',
};

function expiryBadge(expiryDate: string | null): string {
  const days = daysUntil(expiryDate);
  if (days === null) return 'ec-badge bg-surface-muted text-ink-muted';
  if (days < 0) return 'ec-badge-rose';
  if (days <= 30) return 'ec-badge-amber';
  return 'ec-badge-green';
}

export function ConstructionPermitsPage() {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['construction', 'permits', projectId],
    queryFn: () => constructionApi.listPermits(projectId),
    enabled: !!projectId,
  });
  const [editing, setEditing] = useState<Permit | null>(null);
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => constructionApi.deletePermit(projectId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'permits', projectId] });
      toast.success('Permit removed');
    },
  });

  const sorted = (listQ.data ?? []).slice().sort((a, b) => {
    const ax = a.expiry_date ? new Date(a.expiry_date).getTime() : Infinity;
    const bx = b.expiry_date ? new Date(b.expiry_date).getTime() : Infinity;
    return ax - bx;
  });

  const expiringSoon = sorted.filter((p) => {
    const d = daysUntil(p.expiry_date);
    return d !== null && d >= 0 && d <= 30;
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <FileText size={18} className="text-brand-600" /> Permits
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Regulatory permits, sorted by expiry. Rows expiring within 30 days are flagged.
          </p>
        </div>
        <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
          <Plus size={14} /> New permit
        </button>
      </div>

      {expiringSoon.length > 0 && (
        <div className="ec-card border-amber-300 bg-amber-50 p-3 text-sm dark:bg-amber-900/20">
          <p className="flex items-center gap-2 font-semibold text-amber-700 dark:text-amber-300">
            <AlertTriangle size={14} /> {expiringSoon.length} permit{expiringSoon.length === 1 ? '' : 's'} expiring within 30 days
          </p>
        </div>
      )}

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}

      {sorted.length === 0 && !listQ.isLoading && (
        <div className="ec-card flex flex-col items-start gap-3 p-6">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
            <FileText size={22} />
          </div>
          <div>
            <h3 className="font-semibold">No permits logged yet</h3>
            <p className="mt-1 text-sm text-ink-muted">
              Track applications, approvals, and expiry to avoid compliance gaps.
            </p>
          </div>
          <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
            <Plus size={14} /> Add first permit
          </button>
        </div>
      )}

      {sorted.length > 0 && (
        <div className="ec-card overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-surface-muted/40 text-left text-xs uppercase tracking-wider text-ink-subtle">
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Authority</th>
                <th className="px-3 py-2">Reference</th>
                <th className="px-3 py-2">Applied</th>
                <th className="px-3 py-2">Approved</th>
                <th className="px-3 py-2">Expires</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((p) => {
                const days = daysUntil(p.expiry_date);
                const rowClass = days !== null && days < 0
                  ? 'bg-rose-50/40 dark:bg-rose-900/10'
                  : days !== null && days <= 30
                    ? 'bg-amber-50/30 dark:bg-amber-900/10'
                    : '';
                return (
                  <tr
                    key={p.id}
                    className={`cursor-pointer border-b border-border/60 last:border-b-0 hover:bg-surface-muted/30 ${rowClass}`}
                    onClick={() => setEditing(p)}
                  >
                    <td className="px-3 py-2 font-medium">{p.permit_type}</td>
                    <td className="px-3 py-2 text-ink-muted">{p.issuing_authority}</td>
                    <td className="px-3 py-2 font-mono text-xs text-ink-muted">{p.reference_number ?? '—'}</td>
                    <td className="px-3 py-2 text-ink-muted">{shortDate(p.application_date)}</td>
                    <td className="px-3 py-2 text-ink-muted">{shortDate(p.approval_date)}</td>
                    <td className="px-3 py-2">
                      <span className={expiryBadge(p.expiry_date)}>{shortDate(p.expiry_date)}</span>
                    </td>
                    <td className="px-3 py-2 capitalize text-ink-muted">{p.status}</td>
                    <td className="px-3 py-2 text-right">
                      <button
                        type="button"
                        className="ec-btn-ghost !px-1.5 !py-1 text-rose-600"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm(`Delete permit ${p.permit_type}?`)) remove.mutate(p.id);
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
        <PermitModal
          projectId={projectId}
          permit={editing}
          isNew={creating}
          onClose={() => { setCreating(false); setEditing(null); }}
        />
      )}
    </div>
  );
}

function PermitModal({
  projectId,
  permit,
  isNew,
  onClose,
}: {
  projectId: string;
  permit: Permit | null;
  isNew: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<PermitInput>(
    permit
      ? {
          permit_type: permit.permit_type,
          issuing_authority: permit.issuing_authority,
          application_date: permit.application_date,
          approval_date: permit.approval_date,
          expiry_date: permit.expiry_date,
          status: permit.status,
          reference_number: permit.reference_number ?? '',
          conditions: permit.conditions ?? '',
        }
      : EMPTY,
  );

  const update = <K extends keyof PermitInput>(key: K, value: PermitInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const save = useMutation({
    mutationFn: () => {
      if (isNew) return constructionApi.createPermit(projectId, form);
      if (!permit) throw new Error('No permit');
      return constructionApi.updatePermit(projectId, permit.id, form);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'permits', projectId] });
      toast.success(isNew ? 'Permit added' : 'Permit saved');
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
          <p className="font-semibold">{isNew ? 'New permit' : 'Edit permit'}</p>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}><X size={16} /></button>
        </div>
        <form
          className="max-h-[70vh] space-y-3 overflow-y-auto p-5"
          onSubmit={(e) => { e.preventDefault(); save.mutate(); }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="ec-label">Permit type</label>
              <input required className="ec-input" value={form.permit_type}
                onChange={(e) => update('permit_type', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Issuing authority</label>
              <input required className="ec-input" value={form.issuing_authority}
                onChange={(e) => update('issuing_authority', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Reference number</label>
              <input className="ec-input" value={form.reference_number ?? ''}
                onChange={(e) => update('reference_number', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Status</label>
              <input className="ec-input" value={form.status}
                onChange={(e) => update('status', e.target.value)} placeholder="pending / approved / expired" />
            </div>
            <div>
              <label className="ec-label">Application date</label>
              <input type="date" className="ec-input" value={form.application_date}
                onChange={(e) => update('application_date', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Approval date</label>
              <input type="date" className="ec-input" value={form.approval_date ?? ''}
                onChange={(e) => update('approval_date', e.target.value || null)} />
            </div>
            <div className="md:col-span-2">
              <label className="ec-label">Expiry date</label>
              <input type="date" className="ec-input" value={form.expiry_date ?? ''}
                onChange={(e) => update('expiry_date', e.target.value || null)} />
            </div>
          </div>
          <div>
            <label className="ec-label">Conditions</label>
            <textarea className="ec-input min-h-[60px]" value={form.conditions ?? ''}
              onChange={(e) => update('conditions', e.target.value)} />
          </div>
        </form>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="ec-btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? 'Saving…' : isNew ? 'Add permit' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
