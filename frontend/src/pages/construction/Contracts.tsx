import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { FileText, Plus, Trash2, X } from 'lucide-react';
import {
  constructionApi,
  CONTRACT_TYPE_OPTIONS,
  formatMoney,
  shortDate,
  type Contract,
  type ContractInput,
  type ContractType,
} from '../../lib/construction';

const EMPTY: ContractInput = {
  contract_number: '',
  contract_type: 'custom',
  counterparty: '',
  value: '0',
  currency: 'USD',
  signed_date: new Date().toISOString().slice(0, 10),
  start_date: new Date().toISOString().slice(0, 10),
  end_date: new Date().toISOString().slice(0, 10),
  retention_percent: 5,
  defects_liability_period_days: 365,
  payment_terms: '',
};

function typeBadge(t: ContractType): string {
  switch (t) {
    case 'FIDIC': return 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300';
    case 'NEC': return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300';
    case 'JCT': return 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300';
    case 'AIA': return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300';
    case 'custom': return 'bg-surface-muted text-ink-muted';
  }
}

export function ConstructionContractsPage() {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['construction', 'contracts', projectId],
    queryFn: () => constructionApi.listContracts(projectId),
    enabled: !!projectId,
  });
  const [selected, setSelected] = useState<Contract | null>(null);
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => constructionApi.deleteContract(projectId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'contracts', projectId] });
      toast.success('Contract removed');
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <FileText size={18} className="text-brand-600" /> Contracts
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Main and sub-contracts. Click a row to see payment terms and defects liability detail.
          </p>
        </div>
        <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
          <Plus size={14} /> New contract
        </button>
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}

      {listQ.data && listQ.data.length === 0 && (
        <div className="ec-card flex flex-col items-start gap-3 p-6">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
            <FileText size={22} />
          </div>
          <div>
            <h3 className="font-semibold">No contracts logged yet</h3>
            <p className="mt-1 text-sm text-ink-muted">
              Add the main contract first, then add any subcontracts or supply agreements.
            </p>
          </div>
          <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
            <Plus size={14} /> Add first contract
          </button>
        </div>
      )}

      {listQ.data && listQ.data.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {listQ.data.map((c) => (
            <button
              type="button"
              key={c.id}
              onClick={() => setSelected(c)}
              className="ec-card flex flex-col gap-3 p-4 text-left transition hover:border-brand-500/40 hover:bg-surface-muted/30"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-mono text-xs text-ink-muted">{c.contract_number}</p>
                  <p className="mt-1 truncate font-semibold">{c.counterparty}</p>
                </div>
                <span className={`ec-badge ${typeBadge(c.contract_type)}`}>{c.contract_type}</span>
              </div>
              <div className="text-xs text-ink-muted">
                <p>
                  <strong className="text-ink">{formatMoney(c.value, c.currency)}</strong>
                </p>
                <p className="mt-0.5">
                  {shortDate(c.start_date)} → {shortDate(c.end_date)}
                </p>
                <p className="mt-0.5">Signed {shortDate(c.signed_date)}</p>
              </div>
            </button>
          ))}
        </div>
      )}

      {selected && (
        <ContractDetailModal
          projectId={projectId}
          contract={selected}
          onClose={() => setSelected(null)}
          onDelete={() => {
            if (confirm(`Delete contract ${selected.contract_number}?`)) {
              remove.mutate(selected.id);
              setSelected(null);
            }
          }}
        />
      )}
      {creating && (
        <ContractEditorModal
          projectId={projectId}
          contract={null}
          onClose={() => setCreating(false)}
        />
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function ContractDetailModal({
  projectId,
  contract,
  onClose,
  onDelete,
}: {
  projectId: string;
  contract: Contract;
  onClose: () => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <ContractEditorModal
        projectId={projectId}
        contract={contract}
        onClose={() => { setEditing(false); onClose(); }}
      />
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-2xl overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div>
            <p className="font-mono text-xs text-ink-muted">{contract.contract_number}</p>
            <p className="font-semibold">{contract.counterparty}</p>
          </div>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="max-h-[70vh] space-y-4 overflow-y-auto p-5 text-sm">
          <div className="grid gap-3 md:grid-cols-2">
            <Detail label="Type" value={contract.contract_type} />
            <Detail label="Value" value={formatMoney(contract.value, contract.currency)} />
            <Detail label="Signed" value={shortDate(contract.signed_date)} />
            <Detail label="Start" value={shortDate(contract.start_date)} />
            <Detail label="End" value={shortDate(contract.end_date)} />
            <Detail label="Retention" value={`${contract.retention_percent}%`} />
            <Detail
              label="Defects liability"
              value={`${contract.defects_liability_period_days} days`}
            />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-ink-subtle">Payment terms</p>
            <p className="mt-1 whitespace-pre-line text-sm text-ink-muted">
              {contract.payment_terms || '—'}
            </p>
          </div>
        </div>
        <div className="flex justify-between gap-2 border-t border-border px-5 py-3">
          <button type="button" className="ec-btn-ghost text-rose-600" onClick={onDelete}>
            Delete
          </button>
          <div className="flex gap-2">
            <button type="button" className="ec-btn-secondary" onClick={onClose}>Close</button>
            <button type="button" className="ec-btn-primary" onClick={() => setEditing(true)}>
              Edit
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-subtle">{label}</p>
      <p className="mt-0.5 text-sm font-medium">{value}</p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function ContractEditorModal({
  projectId,
  contract,
  onClose,
}: {
  projectId: string;
  contract: Contract | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const isNew = !contract;
  const [form, setForm] = useState<ContractInput>(
    contract
      ? {
          contract_number: contract.contract_number,
          contract_type: contract.contract_type,
          counterparty: contract.counterparty,
          value: contract.value,
          currency: contract.currency,
          signed_date: contract.signed_date,
          start_date: contract.start_date,
          end_date: contract.end_date,
          retention_percent: contract.retention_percent,
          defects_liability_period_days: contract.defects_liability_period_days,
          payment_terms: contract.payment_terms ?? '',
        }
      : EMPTY,
  );

  const update = <K extends keyof ContractInput>(key: K, value: ContractInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const save = useMutation({
    mutationFn: () => {
      if (isNew) return constructionApi.createContract(projectId, form);
      return constructionApi.updateContract(projectId, contract.id, form);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'contracts', projectId] });
      toast.success(isNew ? 'Contract added' : 'Contract saved');
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
          <p className="font-semibold">{isNew ? 'New contract' : 'Edit contract'}</p>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}><X size={16} /></button>
        </div>
        <form
          className="max-h-[70vh] space-y-3 overflow-y-auto p-5"
          onSubmit={(e) => { e.preventDefault(); save.mutate(); }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="ec-label">Contract number</label>
              <input required className="ec-input" value={form.contract_number}
                onChange={(e) => update('contract_number', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Type</label>
              <select
                className="ec-input"
                value={form.contract_type}
                onChange={(e) => update('contract_type', e.target.value as ContractType)}
              >
                {CONTRACT_TYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div className="md:col-span-2">
              <label className="ec-label">Counterparty</label>
              <input required className="ec-input" value={form.counterparty}
                onChange={(e) => update('counterparty', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Value</label>
              <input className="ec-input" inputMode="decimal" value={form.value}
                onChange={(e) => update('value', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Currency</label>
              <input className="ec-input" maxLength={3} value={form.currency}
                onChange={(e) => update('currency', e.target.value.toUpperCase())} />
            </div>
            <div>
              <label className="ec-label">Signed</label>
              <input type="date" className="ec-input" value={form.signed_date}
                onChange={(e) => update('signed_date', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Start</label>
              <input type="date" className="ec-input" value={form.start_date}
                onChange={(e) => update('start_date', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">End</label>
              <input type="date" className="ec-input" value={form.end_date}
                onChange={(e) => update('end_date', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Retention (%)</label>
              <input type="number" min={0} max={100} className="ec-input" value={form.retention_percent}
                onChange={(e) => update('retention_percent', Math.max(0, Math.min(100, Number(e.target.value) || 0)))} />
            </div>
            <div className="md:col-span-2">
              <label className="ec-label">Defects liability period (days)</label>
              <input type="number" min={0} className="ec-input" value={form.defects_liability_period_days}
                onChange={(e) => update('defects_liability_period_days', Math.max(0, Number(e.target.value) || 0))} />
            </div>
          </div>
          <div>
            <label className="ec-label">Payment terms</label>
            <textarea className="ec-input min-h-[100px]" value={form.payment_terms ?? ''}
              onChange={(e) => update('payment_terms', e.target.value)} />
          </div>
        </form>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="ec-btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? 'Saving…' : isNew ? 'Add contract' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
