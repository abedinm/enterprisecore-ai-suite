import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { RefreshCw, X, AlertCircle, CheckCircle2, Clock, Play } from 'lucide-react';
import { jobsApi, type JobOut, type JobDetailOut } from '../../lib/jobs';
import { useAuthStore } from '../../store/auth';
import { formatDateTime } from '../../lib/utils';
import { PermissionDenied } from './OrgLayout';

const STATUS_COLORS: Record<string, string> = {
  queued: 'bg-slate-100 text-slate-700',
  running: 'bg-blue-100 text-blue-700',
  completed: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-rose-100 text-rose-700',
  cancelled: 'bg-amber-100 text-amber-700',
};

const STATUS_ICONS: Record<string, JSX.Element> = {
  queued: <Clock className="w-3 h-3" />,
  running: <Play className="w-3 h-3" />,
  completed: <CheckCircle2 className="w-3 h-3" />,
  failed: <AlertCircle className="w-3 h-3" />,
  cancelled: <X className="w-3 h-3" />,
};

export function JobsTab() {
  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasRole('Admin', 'Manager'));
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [fnFilter, setFnFilter] = useState<string>('');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const listQ = useQuery({
    queryKey: ['jobs', 'list', statusFilter, fnFilter],
    queryFn: () =>
      jobsApi.list({
        status: statusFilter || undefined,
        function_name: fnFilter || undefined,
        limit: 100,
      }),
    enabled: isAdmin,
    refetchInterval: 5000,
  });

  const statsQ = useQuery({
    queryKey: ['jobs', 'stats'],
    queryFn: () => jobsApi.stats(),
    enabled: isAdmin,
    refetchInterval: 5000,
  });

  const detailQ = useQuery({
    queryKey: ['jobs', 'detail', selectedId],
    queryFn: () => jobsApi.get(selectedId!),
    enabled: !!selectedId,
  });

  const cancel = useMutation({
    mutationFn: (id: string) => jobsApi.cancel(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      toast.success('Job cancelled');
    },
    onError: (err: any) =>
      toast.error(err?.response?.data?.detail ?? 'Could not cancel job'),
  });

  const retry = useMutation({
    mutationFn: (id: string) => jobsApi.retry(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      toast.success('Job re-enqueued');
    },
    onError: (err: any) =>
      toast.error(err?.response?.data?.detail ?? 'Could not retry job'),
  });

  if (!isAdmin) {
    return <PermissionDenied what="view background jobs" />;
  }

  const fnOptions = Array.from(
    new Set((listQ.data ?? []).map((j) => j.function_name))
  ).sort();

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard label="Queued" value={statsQ.data?.queued ?? 0} tone="slate" />
        <StatCard label="Running" value={statsQ.data?.running ?? 0} tone="blue" />
        <StatCard label="Completed today" value={statsQ.data?.completed_today ?? 0} tone="emerald" />
        <StatCard label="Failed today" value={statsQ.data?.failed_today ?? 0} tone="rose" />
        <StatCard label="Total" value={statsQ.data?.total ?? 0} tone="slate" />
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="border rounded px-2 py-1 text-sm"
        >
          <option value="">All statuses</option>
          <option value="queued">Queued</option>
          <option value="running">Running</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <select
          value={fnFilter}
          onChange={(e) => setFnFilter(e.target.value)}
          className="border rounded px-2 py-1 text-sm"
        >
          <option value="">All functions</option>
          {fnOptions.map((f) => (
            <option key={f} value={f}>{f}</option>
          ))}
        </select>
        <button
          onClick={() => listQ.refetch()}
          className="text-sm px-2 py-1 border rounded hover:bg-slate-50"
        >
          <RefreshCw className="w-3 h-3 inline" /> Refresh
        </button>
      </div>

      <div className="overflow-x-auto border rounded">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-700">
            <tr>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-left px-3 py-2">Function</th>
              <th className="text-left px-3 py-2">Queue</th>
              <th className="text-left px-3 py-2">Attempts</th>
              <th className="text-left px-3 py-2">Created</th>
              <th className="text-right px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {(listQ.data ?? []).map((j) => (
              <tr key={j.id} className="border-t hover:bg-slate-50">
                <td className="px-3 py-2">
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs ${STATUS_COLORS[j.status] ?? ''}`}
                  >
                    {STATUS_ICONS[j.status]} {j.status}
                  </span>
                </td>
                <td className="px-3 py-2 font-mono text-xs">{j.function_name}</td>
                <td className="px-3 py-2">{j.queue_name}</td>
                <td className="px-3 py-2">{j.attempts}</td>
                <td className="px-3 py-2 text-xs text-slate-500">
                  {formatDateTime(j.created_at)}
                </td>
                <td className="px-3 py-2 text-right space-x-2">
                  <button
                    onClick={() => setSelectedId(j.id)}
                    className="text-blue-600 hover:underline text-xs"
                  >
                    Details
                  </button>
                  {(j.status === 'failed' || j.status === 'completed' || j.status === 'cancelled') && (
                    <button
                      onClick={() => retry.mutate(j.id)}
                      className="text-emerald-600 hover:underline text-xs"
                    >
                      Retry
                    </button>
                  )}
                  {(j.status === 'queued' || j.status === 'running') && (
                    <button
                      onClick={() => cancel.mutate(j.id)}
                      className="text-rose-600 hover:underline text-xs"
                    >
                      Cancel
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {(listQ.data ?? []).length === 0 && (
              <tr>
                <td colSpan={6} className="text-center py-8 text-slate-500">
                  No jobs yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {selectedId && (
        <JobDetailModal
          jobId={selectedId}
          detail={detailQ.data}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  );
}

function StatCard({
  label, value, tone,
}: { label: string; value: number; tone: 'slate' | 'blue' | 'emerald' | 'rose' }) {
  const toneClass = {
    slate: 'border-slate-200',
    blue: 'border-blue-200',
    emerald: 'border-emerald-200',
    rose: 'border-rose-200',
  }[tone];
  return (
    <div className={`border rounded p-3 ${toneClass}`}>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-2xl font-semibold">{value}</div>
    </div>
  );
}

function JobDetailModal({
  jobId, detail, onClose,
}: { jobId: string; detail: JobDetailOut | undefined; onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg max-w-2xl w-full max-h-[80vh] overflow-auto">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h3 className="font-semibold">Job {jobId.slice(0, 12)}â€¦</h3>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-800">
            <X className="w-5 h-5" />
          </button>
        </div>
        {!detail ? (
          <div className="p-6 text-center text-slate-500">Loadingâ€¦</div>
        ) : (
          <div className="p-4 space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <div><span className="text-slate-500">Status:</span> {detail.status}</div>
              <div><span className="text-slate-500">Queue:</span> {detail.queue_name}</div>
              <div><span className="text-slate-500">Attempts:</span> {detail.attempts}</div>
              <div><span className="text-slate-500">RQ id:</span> <code className="text-xs">{detail.rq_job_id ?? 'â€”'}</code></div>
            </div>
            <div>
              <div className="text-xs text-slate-500 mb-1">Function</div>
              <code className="block bg-slate-50 rounded px-2 py-1 text-xs">{detail.function_name}</code>
            </div>
            <div>
              <div className="text-xs text-slate-500 mb-1">Args</div>
              <pre className="bg-slate-50 rounded p-2 text-xs overflow-x-auto">
                {JSON.stringify(detail.args_json, null, 2)}
              </pre>
            </div>
            {detail.last_error && (
              <div>
                <div className="text-xs text-rose-600 mb-1">Last error</div>
                <pre className="bg-rose-50 text-rose-800 rounded p-2 text-xs overflow-x-auto">
                  {detail.last_error}
                </pre>
              </div>
            )}
            {detail.result_excerpt && (
              <div>
                <div className="text-xs text-emerald-600 mb-1">Result excerpt</div>
                <pre className="bg-emerald-50 text-emerald-800 rounded p-2 text-xs overflow-x-auto">
                  {detail.result_excerpt}
                </pre>
              </div>
            )}
            <div>
              <div className="text-xs text-slate-500 mb-1">Attempt history</div>
              <ul className="space-y-1">
                {detail.attempts_history.map((a) => (
                  <li key={a.id} className="border rounded px-2 py-1 text-xs flex justify-between">
                    <span>#{a.attempt_number} {a.status} â€” {a.duration_ms ?? '?'}ms</span>
                    <span className="text-slate-500">{formatDateTime(a.started_at)}</span>
                  </li>
                ))}
                {detail.attempts_history.length === 0 && (
                  <li className="text-slate-500 text-xs">No attempts recorded.</li>
                )}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

