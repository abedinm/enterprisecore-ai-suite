import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ArrowUpDown, Grid2x2, List, Plus, ShieldAlert, Trash2, X } from 'lucide-react';
import {
  constructionApi,
  heatmapCellClass,
  riskSeverity,
  riskSeverityBadge,
  RISK_CATEGORY_OPTIONS,
  shortDate,
  type Risk,
  type RiskCategory,
  type RiskInput,
} from '../../lib/construction';

const EMPTY: RiskInput = {
  title: '',
  description: '',
  category: 'safety',
  probability: 3,
  impact: 3,
  mitigation_plan: '',
  owner_id: null,
  status: 'open',
  identified_at: new Date().toISOString().slice(0, 10),
  due_date: null,
};

type SortKey = 'title' | 'category' | 'probability' | 'impact' | 'score' | 'status' | 'due_date';

export function ConstructionRisksPage() {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['construction', 'risks', projectId],
    queryFn: () => constructionApi.listRisks(projectId),
    enabled: !!projectId,
  });

  const [view, setView] = useState<'table' | 'heatmap'>('table');
  const [sortBy, setSortBy] = useState<SortKey>('score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [editing, setEditing] = useState<Risk | null>(null);
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => constructionApi.deleteRisk(projectId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'risks', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'dashboard', projectId] });
      toast.success('Risk removed');
    },
  });

  const sorted = useMemo(() => {
    const rows = [...(listQ.data ?? [])];
    rows.sort((a, b) => {
      const av = (a[sortBy] ?? '') as string | number;
      const bv = (b[sortBy] ?? '') as string | number;
      if (av === bv) return 0;
      const dir = sortDir === 'asc' ? 1 : -1;
      return av > bv ? dir : -dir;
    });
    return rows;
  }, [listQ.data, sortBy, sortDir]);

  function setSort(key: SortKey) {
    if (sortBy === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(key);
      setSortDir(key === 'title' || key === 'category' ? 'asc' : 'desc');
    }
  }

  const heatmapRisks = useMemo(() => {
    const grid: Risk[][][] = Array.from({ length: 5 }, () =>
      Array.from({ length: 5 }, () => [] as Risk[]),
    );
    for (const r of listQ.data ?? []) {
      const p = Math.min(5, Math.max(1, r.probability));
      const i = Math.min(5, Math.max(1, r.impact));
      grid[p - 1][i - 1].push(r);
    }
    return grid;
  }, [listQ.data]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <ShieldAlert size={18} className="text-rose-600" /> Risk register
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            All identified risks, scored by probability × impact (1-25).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="ec-card flex items-center gap-1 p-1">
            <button
              type="button"
              className={`flex items-center gap-1 rounded-md px-2 py-1 text-xs ${view === 'table' ? 'bg-brand-600 text-white' : 'text-ink-muted'}`}
              onClick={() => setView('table')}
            >
              <List size={12} /> Table
            </button>
            <button
              type="button"
              className={`flex items-center gap-1 rounded-md px-2 py-1 text-xs ${view === 'heatmap' ? 'bg-brand-600 text-white' : 'text-ink-muted'}`}
              onClick={() => setView('heatmap')}
            >
              <Grid2x2 size={12} /> Heatmap
            </button>
          </div>
          <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
            <Plus size={14} /> New risk
          </button>
        </div>
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading risks…</p>}

      {listQ.data && listQ.data.length === 0 && (
        <div className="ec-card flex flex-col items-start gap-3 p-6">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-rose-500/10 text-rose-600">
            <ShieldAlert size={22} />
          </div>
          <div>
            <h3 className="font-semibold">No risks logged yet</h3>
            <p className="mt-1 text-sm text-ink-muted">
              Capture your first risk to start building the project risk register.
            </p>
          </div>
          <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
            <Plus size={14} /> Create first risk
          </button>
        </div>
      )}

      {listQ.data && listQ.data.length > 0 && view === 'table' && (
        <div className="ec-card overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-surface-muted/40 text-left text-xs uppercase tracking-wider text-ink-subtle">
                <SortableTh label="Title" col="title" sortBy={sortBy} sortDir={sortDir} onSort={setSort} />
                <SortableTh label="Category" col="category" sortBy={sortBy} sortDir={sortDir} onSort={setSort} />
                <SortableTh label="Prob" col="probability" sortBy={sortBy} sortDir={sortDir} onSort={setSort} />
                <SortableTh label="Impact" col="impact" sortBy={sortBy} sortDir={sortDir} onSort={setSort} />
                <SortableTh label="Score" col="score" sortBy={sortBy} sortDir={sortDir} onSort={setSort} />
                <th className="px-3 py-2">Severity</th>
                <th className="px-3 py-2">Owner</th>
                <SortableTh label="Status" col="status" sortBy={sortBy} sortDir={sortDir} onSort={setSort} />
                <SortableTh label="Due" col="due_date" sortBy={sortBy} sortDir={sortDir} onSort={setSort} />
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((r) => {
                const sev = riskSeverity(r.score);
                return (
                  <tr
                    key={r.id}
                    className="cursor-pointer border-b border-border/60 last:border-b-0 hover:bg-surface-muted/30"
                    onClick={() => setEditing(r)}
                  >
                    <td className="px-3 py-2 font-medium">{r.title}</td>
                    <td className="px-3 py-2 capitalize text-ink-muted">{r.category}</td>
                    <td className="px-3 py-2 font-mono">{r.probability}</td>
                    <td className="px-3 py-2 font-mono">{r.impact}</td>
                    <td className="px-3 py-2 font-mono">{r.score}</td>
                    <td className="px-3 py-2">
                      <span className={riskSeverityBadge(sev)}>{sev}</span>
                    </td>
                    <td className="px-3 py-2 text-ink-muted">{r.owner_name ?? '—'}</td>
                    <td className="px-3 py-2 capitalize text-ink-muted">{r.status}</td>
                    <td className="px-3 py-2 text-ink-muted">{shortDate(r.due_date)}</td>
                    <td className="px-3 py-2 text-right">
                      <button
                        type="button"
                        className="ec-btn-ghost !px-1.5 !py-1 text-rose-600"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm(`Delete risk "${r.title}"?`)) remove.mutate(r.id);
                        }}
                        title="Delete"
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

      {listQ.data && listQ.data.length > 0 && view === 'heatmap' && (
        <div className="ec-card overflow-x-auto p-4">
          <table className="border-separate border-spacing-1">
            <thead>
              <tr>
                <th></th>
                {[1, 2, 3, 4, 5].map((i) => (
                  <th key={i} className="px-2 text-center text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
                    Impact {i}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[5, 4, 3, 2, 1].map((p) => (
                <tr key={p}>
                  <th className="pr-2 text-right text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
                    Prob {p}
                  </th>
                  {[1, 2, 3, 4, 5].map((i) => {
                    const cellRisks = heatmapRisks[p - 1][i - 1];
                    return (
                      <td
                        key={`${p}-${i}`}
                        className={`min-h-[80px] w-32 align-top rounded-md p-1.5 text-left text-xs ${heatmapCellClass(p, i)}`}
                        style={{ minHeight: 80 }}
                      >
                        {cellRisks.length === 0 && <span className="text-white/40">·</span>}
                        <div className="space-y-1">
                          {cellRisks.map((r) => (
                            <button
                              key={r.id}
                              type="button"
                              onClick={() => setEditing(r)}
                              className="block w-full truncate rounded bg-white/15 px-1.5 py-0.5 text-left text-[11px] font-medium hover:bg-white/30"
                              title={r.title}
                            >
                              {r.title}
                            </button>
                          ))}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(creating || editing) && (
        <RiskModal
          projectId={projectId}
          risk={editing}
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

function SortableTh({
  label,
  col,
  sortBy,
  sortDir,
  onSort,
}: {
  label: string;
  col: SortKey;
  sortBy: SortKey;
  sortDir: 'asc' | 'desc';
  onSort: (col: SortKey) => void;
}) {
  const active = sortBy === col;
  return (
    <th
      className="cursor-pointer select-none px-3 py-2 hover:text-ink"
      onClick={() => onSort(col)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <ArrowUpDown size={11} className={active ? 'text-ink' : 'opacity-50'} />
        {active && <span className="text-[10px]">{sortDir === 'asc' ? '↑' : '↓'}</span>}
      </span>
    </th>
  );
}

/* -------------------------------------------------------------------------- */

function RiskModal({
  projectId,
  risk,
  isNew,
  onClose,
}: {
  projectId: string;
  risk: Risk | null;
  isNew: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<RiskInput>(
    risk
      ? {
          title: risk.title,
          description: risk.description ?? '',
          category: risk.category,
          probability: risk.probability,
          impact: risk.impact,
          mitigation_plan: risk.mitigation_plan ?? '',
          owner_id: risk.owner_id ?? null,
          status: risk.status,
          identified_at: risk.identified_at,
          due_date: risk.due_date,
        }
      : EMPTY,
  );

  const update = <K extends keyof RiskInput>(key: K, value: RiskInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const save = useMutation({
    mutationFn: () => {
      if (isNew) return constructionApi.createRisk(projectId, form);
      if (!risk) throw new Error('No risk');
      return constructionApi.updateRisk(projectId, risk.id, form);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'risks', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'dashboard', projectId] });
      toast.success(isNew ? 'Risk created' : 'Risk saved');
      onClose();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } }; message?: string })
        .response?.data?.detail ?? (err as Error).message ?? 'Failed';
      toast.error(typeof detail === 'string' ? detail : 'Failed');
    },
  });

  const liveScore = (form.probability ?? 0) * (form.impact ?? 0);
  const liveSev = riskSeverity(liveScore);

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-2xl overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-ink-subtle">
              {isNew ? 'New risk' : 'Edit risk'}
            </p>
            <p className="font-semibold">{form.title || 'Untitled risk'}</p>
          </div>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <form
          className="max-h-[70vh] space-y-3 overflow-y-auto p-5"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div>
            <label className="ec-label">Title</label>
            <input
              required
              className="ec-input"
              value={form.title}
              onChange={(e) => update('title', e.target.value)}
            />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="ec-label">Category</label>
              <select
                className="ec-input"
                value={form.category}
                onChange={(e) => update('category', e.target.value as RiskCategory)}
              >
                {RISK_CATEGORY_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="ec-label">Status</label>
              <input
                className="ec-input"
                value={form.status}
                onChange={(e) => update('status', e.target.value)}
                placeholder="open / mitigated / closed"
              />
            </div>
            <div>
              <label className="ec-label">Probability (1-5)</label>
              <input
                type="number"
                min={1}
                max={5}
                className="ec-input"
                value={form.probability}
                onChange={(e) => update('probability', Math.max(1, Math.min(5, Number(e.target.value) || 1)))}
              />
            </div>
            <div>
              <label className="ec-label">Impact (1-5)</label>
              <input
                type="number"
                min={1}
                max={5}
                className="ec-input"
                value={form.impact}
                onChange={(e) => update('impact', Math.max(1, Math.min(5, Number(e.target.value) || 1)))}
              />
            </div>
          </div>
          <div className="flex items-center gap-3 rounded-md border border-border bg-surface-muted/40 px-3 py-2 text-xs">
            <span className="text-ink-muted">Computed score</span>
            <span className="font-mono text-sm font-semibold">{liveScore}</span>
            <span className={riskSeverityBadge(liveSev)}>{liveSev}</span>
          </div>
          <div>
            <label className="ec-label">Description</label>
            <textarea
              className="ec-input min-h-[80px]"
              value={form.description ?? ''}
              onChange={(e) => update('description', e.target.value)}
            />
          </div>
          <div>
            <label className="ec-label">Mitigation plan</label>
            <textarea
              className="ec-input min-h-[80px]"
              value={form.mitigation_plan ?? ''}
              onChange={(e) => update('mitigation_plan', e.target.value)}
            />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="ec-label">Identified</label>
              <input
                type="date"
                className="ec-input"
                value={form.identified_at}
                onChange={(e) => update('identified_at', e.target.value)}
              />
            </div>
            <div>
              <label className="ec-label">Due date</label>
              <input
                type="date"
                className="ec-input"
                value={form.due_date ?? ''}
                onChange={(e) => update('due_date', e.target.value || null)}
              />
            </div>
          </div>
        </form>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="ec-btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? 'Saving…' : isNew ? 'Create risk' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
