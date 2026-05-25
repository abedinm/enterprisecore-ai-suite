import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Camera, CloudSun, Plus, Trash2, TrendingUp, Users, X } from 'lucide-react';
import {
  constructionApi,
  shortDate,
  type ProgressReportInput,
} from '../../lib/construction';

const EMPTY: ProgressReportInput = {
  report_date: new Date().toISOString().slice(0, 10),
  overall_progress_percent: 0,
  narrative: '',
  reported_by_id: null,
  photos: [],
  weather_conditions: '',
  workforce_count: 0,
};

export function ConstructionProgressPage() {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['construction', 'progress-reports', projectId],
    queryFn: () => constructionApi.listProgressReports(projectId),
    enabled: !!projectId,
  });

  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => constructionApi.deleteProgressReport(projectId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'progress-reports', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'dashboard', projectId] });
      toast.success('Report removed');
    },
  });

  const sorted = (listQ.data ?? []).slice().sort(
    (a, b) => new Date(b.report_date).getTime() - new Date(a.report_date).getTime(),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <TrendingUp size={18} className="text-brand-600" /> Progress reports
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Daily, weekly, or ad-hoc reports of on-site progress, weather, and crew.
          </p>
        </div>
        <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
          <Plus size={14} /> New report
        </button>
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}

      {sorted.length === 0 && !listQ.isLoading && (
        <div className="ec-card flex flex-col items-start gap-3 p-6">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
            <TrendingUp size={22} />
          </div>
          <div>
            <h3 className="font-semibold">No progress reports yet</h3>
            <p className="mt-1 text-sm text-ink-muted">
              File your first report to start tracking on-site progress.
            </p>
          </div>
          <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
            <Plus size={14} /> File first report
          </button>
        </div>
      )}

      <div className="space-y-3">
        {sorted.map((r) => (
          <article key={r.id} className="ec-card p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="font-semibold">{shortDate(r.report_date)}</p>
                <div className="mt-2 flex items-center gap-2">
                  <div className="h-2 w-40 overflow-hidden rounded-full bg-surface-muted">
                    <div
                      className="h-full bg-brand-600"
                      style={{ width: `${Math.min(100, Math.max(0, r.overall_progress_percent))}%` }}
                    />
                  </div>
                  <span className="font-mono text-sm font-semibold">{r.overall_progress_percent}%</span>
                </div>
              </div>
              <button
                type="button"
                className="ec-btn-ghost !px-1.5 !py-1 text-rose-600"
                onClick={() => {
                  if (confirm('Delete this report?')) remove.mutate(r.id);
                }}
              >
                <Trash2 size={14} />
              </button>
            </div>
            <p className="mt-3 whitespace-pre-line text-sm text-ink-muted">{r.narrative}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
              {r.weather_conditions && (
                <span className="ec-badge bg-surface-muted text-ink-muted inline-flex items-center gap-1">
                  <CloudSun size={11} /> {r.weather_conditions}
                </span>
              )}
              {r.workforce_count != null && (
                <span className="ec-badge bg-surface-muted text-ink-muted inline-flex items-center gap-1">
                  <Users size={11} /> {r.workforce_count} workers
                </span>
              )}
              {r.photos.length > 0 && (
                <span className="ec-badge bg-surface-muted text-ink-muted inline-flex items-center gap-1">
                  <Camera size={11} /> {r.photos.length} {r.photos.length === 1 ? 'photo' : 'photos'}
                </span>
              )}
            </div>
          </article>
        ))}
      </div>

      {creating && (
        <ProgressModal
          projectId={projectId}
          onClose={() => setCreating(false)}
        />
      )}
    </div>
  );
}

function ProgressModal({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<ProgressReportInput>(EMPTY);
  const [photoStr, setPhotoStr] = useState('');

  const update = <K extends keyof ProgressReportInput>(key: K, value: ProgressReportInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const save = useMutation({
    mutationFn: () => {
      const photos = photoStr
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);
      return constructionApi.createProgressReport(projectId, { ...form, photos });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'progress-reports', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'dashboard', projectId] });
      toast.success('Report filed');
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
          <p className="font-semibold">New progress report</p>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}><X size={16} /></button>
        </div>
        <form
          className="max-h-[70vh] space-y-3 overflow-y-auto p-5"
          onSubmit={(e) => { e.preventDefault(); save.mutate(); }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="ec-label">Report date</label>
              <input type="date" required className="ec-input" value={form.report_date}
                onChange={(e) => update('report_date', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Overall progress (%)</label>
              <input type="number" min={0} max={100} className="ec-input" value={form.overall_progress_percent}
                onChange={(e) => update('overall_progress_percent',
                  Math.max(0, Math.min(100, Number(e.target.value) || 0)))} />
            </div>
            <div>
              <label className="ec-label">Weather</label>
              <input className="ec-input" value={form.weather_conditions ?? ''}
                onChange={(e) => update('weather_conditions', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Workforce count</label>
              <input type="number" min={0} className="ec-input" value={form.workforce_count ?? 0}
                onChange={(e) => update('workforce_count', Math.max(0, Number(e.target.value) || 0))} />
            </div>
          </div>
          <div>
            <label className="ec-label">Narrative</label>
            <textarea required className="ec-input min-h-[120px]" value={form.narrative}
              onChange={(e) => update('narrative', e.target.value)} />
          </div>
          <div>
            <label className="ec-label">Photo URLs (one per line)</label>
            <textarea className="ec-input min-h-[60px] font-mono text-xs" value={photoStr}
              onChange={(e) => setPhotoStr(e.target.value)} />
          </div>
        </form>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="ec-btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? 'Saving…' : 'File report'}
          </button>
        </div>
      </div>
    </div>
  );
}
