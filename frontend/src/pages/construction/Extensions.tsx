import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Clock, Plus, Trash2, X } from 'lucide-react';
import {
  constructionApi,
  shortDate,
  type EOTRequest,
  type EOTRequestInput,
} from '../../lib/construction';

const EMPTY: EOTRequestInput = {
  requested_days: 0,
  reason: '',
  supporting_evidence: '',
  claim_date: new Date().toISOString().slice(0, 10),
  status: 'pending',
  granted_days: null,
  decided_at: null,
  decision_notes: '',
};

function statusBadge(status: string): string {
  const s = status.toLowerCase();
  if (s.includes('grant') || s.includes('approve')) return 'ec-badge-green';
  if (s.includes('reject') || s.includes('denied')) return 'ec-badge-rose';
  if (s.includes('pending') || s.includes('review')) return 'ec-badge-amber';
  return 'ec-badge-blue';
}

export function ConstructionExtensionsPage() {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['construction', 'eot-requests', projectId],
    queryFn: () => constructionApi.listEotRequests(projectId),
    enabled: !!projectId,
  });
  const [editing, setEditing] = useState<EOTRequest | null>(null);
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => constructionApi.deleteEotRequest(projectId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'eot-requests', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'dashboard', projectId] });
      toast.success('EOT removed');
    },
  });

  const sorted = (listQ.data ?? []).slice().sort(
    (a, b) => new Date(b.claim_date).getTime() - new Date(a.claim_date).getTime(),
  );

  const totalRequested = sorted.reduce((a, r) => a + r.requested_days, 0);
  const totalGranted = sorted.reduce((a, r) => a + (r.granted_days ?? 0), 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Clock size={18} className="text-brand-600" /> Extension of time (EOT)
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Time-only claims for delays beyond the contractor's control.
          </p>
        </div>
        <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
          <Plus size={14} /> New EOT
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="ec-card p-4">
          <p className="text-xs uppercase tracking-wider text-ink-subtle">Total requested</p>
          <p className="mt-1 text-2xl font-semibold">{totalRequested} days</p>
        </div>
        <div className="ec-card p-4">
          <p className="text-xs uppercase tracking-wider text-ink-subtle">Total granted</p>
          <p className="mt-1 text-2xl font-semibold text-emerald-600">{totalGranted} days</p>
        </div>
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}

      {sorted.length === 0 && !listQ.isLoading && (
        <div className="ec-card flex flex-col items-start gap-3 p-6">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
            <Clock size={22} />
          </div>
          <div>
            <h3 className="font-semibold">No extension requests</h3>
            <p className="mt-1 text-sm text-ink-muted">
              File an EOT to capture time-impact-only claims.
            </p>
          </div>
          <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
            <Plus size={14} /> File first EOT
          </button>
        </div>
      )}

      {sorted.length > 0 && (
        <div className="space-y-2">
          {sorted.map((r) => (
            <div
              key={r.id}
              className="ec-card cursor-pointer p-4 hover:border-brand-500/40 hover:bg-surface-muted/30"
              onClick={() => setEditing(r)}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold">Claim {shortDate(r.claim_date)}</p>
                    <span className={statusBadge(r.status)}>{r.status}</span>
                  </div>
                  <p className="mt-1 text-sm text-ink-muted line-clamp-2">{r.reason}</p>
                </div>
                <div className="flex items-center gap-3 text-xs text-ink-muted">
                  <div className="text-center">
                    <p className="font-mono text-lg font-semibold text-ink">{r.requested_days}d</p>
                    <p className="text-[10px] uppercase tracking-wider">Requested</p>
                  </div>
                  <span className="text-ink-subtle">→</span>
                  <div className="text-center">
                    <p className={`font-mono text-lg font-semibold ${r.granted_days != null ? 'text-emerald-600' : 'text-ink-subtle'}`}>
                      {r.granted_days ?? '—'}{r.granted_days != null ? 'd' : ''}
                    </p>
                    <p className="text-[10px] uppercase tracking-wider">Granted</p>
                  </div>
                  <button
                    type="button"
                    className="ec-btn-ghost !px-1.5 !py-1 text-rose-600"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm('Delete EOT request?')) remove.mutate(r.id);
                    }}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {(editing || creating) && (
        <EotModal
          projectId={projectId}
          eot={editing}
          isNew={creating}
          onClose={() => { setCreating(false); setEditing(null); }}
        />
      )}
    </div>
  );
}

function EotModal({
  projectId,
  eot,
  isNew,
  onClose,
}: {
  projectId: string;
  eot: EOTRequest | null;
  isNew: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<EOTRequestInput>(
    eot
      ? {
          requested_days: eot.requested_days,
          reason: eot.reason,
          supporting_evidence: eot.supporting_evidence ?? '',
          claim_date: eot.claim_date,
          status: eot.status,
          granted_days: eot.granted_days,
          decided_at: eot.decided_at,
          decision_notes: eot.decision_notes ?? '',
        }
      : EMPTY,
  );

  const update = <K extends keyof EOTRequestInput>(key: K, value: EOTRequestInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const save = useMutation({
    mutationFn: () => {
      if (isNew) return constructionApi.createEotRequest(projectId, form);
      if (!eot) throw new Error('No EOT');
      return constructionApi.updateEotRequest(projectId, eot.id, form);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'eot-requests', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'dashboard', projectId] });
      toast.success(isNew ? 'EOT filed' : 'EOT saved');
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
          <p className="font-semibold">{isNew ? 'New EOT request' : 'Edit EOT'}</p>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}><X size={16} /></button>
        </div>
        <form
          className="max-h-[70vh] space-y-3 overflow-y-auto p-5"
          onSubmit={(e) => { e.preventDefault(); save.mutate(); }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="ec-label">Requested days</label>
              <input type="number" min={0} className="ec-input" value={form.requested_days}
                onChange={(e) => update('requested_days', Math.max(0, Number(e.target.value) || 0))} />
            </div>
            <div>
              <label className="ec-label">Granted days</label>
              <input type="number" min={0} className="ec-input" value={form.granted_days ?? ''}
                onChange={(e) => update('granted_days', e.target.value === '' ? null : Number(e.target.value) || 0)} />
            </div>
            <div>
              <label className="ec-label">Claim date</label>
              <input type="date" className="ec-input" value={form.claim_date}
                onChange={(e) => update('claim_date', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Decided at</label>
              <input type="date" className="ec-input" value={form.decided_at ?? ''}
                onChange={(e) => update('decided_at', e.target.value || null)} />
            </div>
            <div className="md:col-span-2">
              <label className="ec-label">Status</label>
              <input className="ec-input" value={form.status}
                onChange={(e) => update('status', e.target.value)}
                placeholder="pending / under review / granted / rejected" />
            </div>
          </div>
          <div>
            <label className="ec-label">Reason</label>
            <textarea required className="ec-input min-h-[80px]" value={form.reason}
              onChange={(e) => update('reason', e.target.value)} />
          </div>
          <div>
            <label className="ec-label">Supporting evidence</label>
            <textarea className="ec-input min-h-[60px]" value={form.supporting_evidence ?? ''}
              onChange={(e) => update('supporting_evidence', e.target.value)} />
          </div>
          <div>
            <label className="ec-label">Decision notes</label>
            <textarea className="ec-input min-h-[60px]" value={form.decision_notes ?? ''}
              onChange={(e) => update('decision_notes', e.target.value)} />
          </div>
        </form>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="ec-btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? 'Saving…' : isNew ? 'File EOT' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
