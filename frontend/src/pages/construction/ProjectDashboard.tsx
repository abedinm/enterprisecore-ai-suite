import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  Calendar,
  CalendarClock,
  CircleDollarSign,
  ClipboardList,
  Clock,
  FileText,
  Flag,
  Percent,
  ShieldAlert,
  TrendingUp,
} from 'lucide-react';
import {
  constructionApi,
  daysUntil,
  formatMoney,
  heatmapCellClass,
  shortDate,
} from '../../lib/construction';

function StatTile({
  label,
  value,
  hint,
  icon: Icon,
  tone = 'default',
  to,
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon: typeof Percent;
  tone?: 'default' | 'good' | 'warn' | 'bad';
  to?: string;
}) {
  const toneClass = {
    default: 'bg-brand-600/10 text-brand-600',
    good: 'bg-emerald-500/10 text-emerald-600',
    warn: 'bg-amber-500/10 text-amber-600',
    bad: 'bg-rose-500/10 text-rose-600',
  }[tone];
  const body = (
    <>
      <div>
        <p className="text-xs uppercase tracking-wider text-ink-subtle">{label}</p>
        <p className="mt-1 text-2xl font-semibold">{value}</p>
        {hint && <p className="mt-1 text-xs text-ink-muted">{hint}</p>}
      </div>
      <div className={`grid h-10 w-10 place-items-center rounded-xl ${toneClass}`}>
        <Icon size={18} />
      </div>
    </>
  );
  return to ? (
    <Link
      to={to}
      className="ec-card flex items-center justify-between p-4 transition hover:border-brand-500/40 hover:bg-surface-muted/30"
    >
      {body}
    </Link>
  ) : (
    <div className="ec-card flex items-center justify-between p-4">{body}</div>
  );
}

export function ConstructionDashboardPage() {
  const { projectId = '' } = useParams<{ projectId: string }>();

  const dashboardQ = useQuery({
    queryKey: ['construction', 'dashboard', projectId],
    queryFn: () => constructionApi.getDashboard(projectId),
    enabled: !!projectId,
  });

  // For the heatmap we render full risk list cells.
  const risksQ = useQuery({
    queryKey: ['construction', 'risks', projectId],
    queryFn: () => constructionApi.listRisks(projectId),
    enabled: !!projectId,
  });

  const heatmap = useMemo(() => {
    const grid: number[][] = Array.from({ length: 5 }, () => Array(5).fill(0));
    for (const r of risksQ.data ?? []) {
      const p = Math.min(5, Math.max(1, r.probability));
      const i = Math.min(5, Math.max(1, r.impact));
      grid[p - 1][i - 1] += 1;
    }
    return grid;
  }, [risksQ.data]);

  if (dashboardQ.isLoading) {
    return <p className="text-sm text-ink-muted">Loading dashboard…</p>;
  }
  if (dashboardQ.isError || !dashboardQ.data) {
    return (
      <div className="ec-card border-rose-300 bg-rose-50 p-4 text-sm text-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
        <p className="font-semibold">Could not load project dashboard</p>
        <p className="mt-1">
          The project may not exist or your license may not include the construction module.
        </p>
      </div>
    );
  }

  const d = dashboardQ.data;
  const remaining = daysUntil(d.project.expected_end_date);
  const remainingHint =
    remaining === null
      ? undefined
      : remaining < 0
        ? `${Math.abs(remaining)} days overdue`
        : `${remaining} days remaining`;
  const remainingTone: 'good' | 'warn' | 'bad' =
    remaining === null || remaining > 30 ? 'good' : remaining >= 0 ? 'warn' : 'bad';

  const variationsTone: 'good' | 'warn' | 'bad' =
    d.open_variations_count === 0
      ? 'good'
      : d.open_variations_count >= 5
        ? 'bad'
        : 'warn';

  const base = `/construction/projects/${projectId}`;

  return (
    <div className="space-y-5">
      {/* Project header */}
      <div className="ec-card flex flex-wrap items-start justify-between gap-3 p-5">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wider text-ink-subtle">Project</p>
          <h2 className="mt-1 text-xl font-semibold">{d.project.name}</h2>
          <p className="mt-1 text-xs text-ink-muted">
            {d.project.client_name} · {d.project.location} · {d.project.status}
          </p>
        </div>
        <div className="flex flex-col items-end text-xs text-ink-muted">
          <span>Started {shortDate(d.project.start_date)}</span>
          <span>Expected end {shortDate(d.project.expected_end_date)}</span>
        </div>
      </div>

      {/* Top KPI row */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Contract value"
          value={formatMoney(d.project.contract_value, d.project.currency)}
          icon={CircleDollarSign}
        />
        <StatTile
          label="Schedule progress"
          value={`${d.schedule_progress_percent}%`}
          icon={TrendingUp}
          tone={d.schedule_progress_percent >= 75 ? 'good' : 'default'}
          to={`${base}/schedule`}
        />
        <StatTile
          label="Days remaining"
          value={remaining === null ? '—' : remaining}
          hint={remainingHint}
          icon={CalendarClock}
          tone={remainingTone}
        />
        <StatTile
          label="Open variations"
          value={d.open_variations_count}
          hint={`Impact ${formatMoney(d.open_variations_cost_impact, d.project.currency)}`}
          icon={ClipboardList}
          tone={variationsTone}
          to={`${base}/variations`}
        />
      </div>

      {/* Body grid */}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        {/* Left column: heatmap + milestones */}
        <div className="space-y-4">
          {/* Risk heatmap */}
          <div className="ec-card overflow-hidden">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div>
                <p className="font-semibold flex items-center gap-2">
                  <ShieldAlert size={16} className="text-rose-600" />
                  Risk heatmap
                </p>
                <p className="mt-0.5 text-xs text-ink-muted">
                  Probability × impact. Each cell counts the risks at that score.
                </p>
              </div>
              <Link to={`${base}/risks`} className="ec-btn-ghost text-xs">
                Open risks <ArrowRight size={12} />
              </Link>
            </div>
            <div className="overflow-x-auto p-4">
              <table className="border-separate border-spacing-1">
                <thead>
                  <tr>
                    <th className="text-[10px] uppercase tracking-wider text-ink-subtle"></th>
                    {[1, 2, 3, 4, 5].map((i) => (
                      <th
                        key={i}
                        className="px-2 text-center text-[10px] font-semibold uppercase tracking-wider text-ink-muted"
                      >
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
                        const count = heatmap[p - 1][i - 1];
                        return (
                          <td
                            key={`${p}-${i}`}
                            className={`h-12 w-14 rounded-md text-center align-middle text-sm font-semibold ${heatmapCellClass(p, i)}`}
                          >
                            {count > 0 ? count : ''}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
                <div className="flex items-center gap-1.5">
                  <span className="h-3 w-3 rounded-sm bg-emerald-500/50" /> Low
                  <span className="ml-1 text-ink-muted">{d.risks_by_severity.low}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="h-3 w-3 rounded-sm bg-blue-500/60" /> Medium
                  <span className="ml-1 text-ink-muted">{d.risks_by_severity.medium}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="h-3 w-3 rounded-sm bg-amber-500/70" /> High
                  <span className="ml-1 text-ink-muted">{d.risks_by_severity.high}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="h-3 w-3 rounded-sm bg-rose-500/80" /> Critical
                  <span className="ml-1 text-ink-muted">{d.risks_by_severity.critical}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Upcoming milestones */}
          <div className="ec-card overflow-hidden">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <p className="font-semibold flex items-center gap-2">
                <Flag size={16} className="text-brand-600" />
                Upcoming milestones (30 days)
              </p>
              <Link to={`${base}/milestones`} className="ec-btn-ghost text-xs">
                Open <ArrowRight size={12} />
              </Link>
            </div>
            {d.upcoming_milestones.length === 0 ? (
              <p className="p-5 text-sm text-ink-muted">
                No milestones scheduled within the next 30 days.
              </p>
            ) : (
              <ul>
                {d.upcoming_milestones.map((m) => (
                  <li
                    key={m.id}
                    className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 border-b border-border/60 px-4 py-3 last:border-b-0"
                  >
                    <span className="grid h-8 w-8 place-items-center rounded-md bg-brand-600/10 text-brand-600">
                      <Calendar size={14} />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{m.name}</p>
                      <p className="text-xs text-ink-muted">{shortDate(m.planned_date)}</p>
                    </div>
                    {m.payment_trigger && (
                      <span className="ec-badge-amber">
                        Payment {m.payment_amount ? formatMoney(m.payment_amount, d.project.currency) : ''}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Right column: insurances, instructions, progress excerpt */}
        <div className="space-y-4">
          {d.pending_eot_days > 0 && (
            <div className="ec-card flex items-start gap-3 border-amber-300 bg-amber-50 p-4 text-sm dark:bg-amber-900/20">
              <Clock size={16} className="mt-0.5 shrink-0 text-amber-600" />
              <p className="text-amber-700 dark:text-amber-300">
                Pending EOT claims totalling{' '}
                <strong>{d.pending_eot_days} days</strong>.{' '}
                <Link to={`${base}/extensions`} className="font-medium underline">
                  Review extensions
                </Link>
              </p>
            </div>
          )}

          {d.expiring_insurances.length > 0 && (
            <div className="ec-card overflow-hidden border-amber-300/60">
              <div className="flex items-center justify-between border-b border-border bg-amber-50/40 px-4 py-3 dark:bg-amber-900/10">
                <p className="font-semibold flex items-center gap-2">
                  <AlertTriangle size={16} className="text-amber-600" />
                  Expiring insurances
                </p>
                <Link to={`${base}/insurances`} className="ec-btn-ghost text-xs">
                  Open <ArrowRight size={12} />
                </Link>
              </div>
              <ul>
                {d.expiring_insurances.map((ins) => {
                  const days = daysUntil(ins.expiry_date);
                  return (
                    <li
                      key={ins.id}
                      className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 border-b border-border/60 px-4 py-2.5 last:border-b-0"
                    >
                      <span className="ec-badge bg-surface-muted text-ink-muted">
                        {ins.insurance_type}
                      </span>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{ins.provider}</p>
                        <p className="text-xs text-ink-muted">{ins.policy_number}</p>
                      </div>
                      <span
                        className={
                          days !== null && days <= 14
                            ? 'ec-badge-rose'
                            : 'ec-badge-amber'
                        }
                      >
                        {days === null
                          ? 'No expiry'
                          : days < 0
                            ? `${Math.abs(days)}d overdue`
                            : `${days}d left`}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          <div className="ec-card overflow-hidden">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <p className="font-semibold flex items-center gap-2">
                <ClipboardList size={16} className="text-brand-600" />
                Recent site instructions
              </p>
              <Link to={`${base}/site-instructions`} className="ec-btn-ghost text-xs">
                Open <ArrowRight size={12} />
              </Link>
            </div>
            {d.recent_site_instructions.length === 0 ? (
              <p className="p-5 text-sm text-ink-muted">No site instructions issued.</p>
            ) : (
              <ul>
                {d.recent_site_instructions.map((si) => (
                  <li
                    key={si.id}
                    className="border-b border-border/60 px-4 py-2.5 last:border-b-0"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="truncate text-sm font-medium">
                        <span className="font-mono text-xs text-ink-muted">{si.number}</span>{' '}
                        {si.title}
                      </p>
                      <span className="ec-badge bg-surface-muted text-ink-muted">{si.status}</span>
                    </div>
                    <p className="mt-0.5 text-xs text-ink-muted">{shortDate(si.issued_at)}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="ec-card overflow-hidden">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <p className="font-semibold flex items-center gap-2">
                <FileText size={16} className="text-brand-600" />
                Latest progress report
              </p>
              <Link to={`${base}/progress`} className="ec-btn-ghost text-xs">
                Open <ArrowRight size={12} />
              </Link>
            </div>
            {!d.latest_progress_report ? (
              <p className="p-5 text-sm text-ink-muted">No progress reports filed yet.</p>
            ) : (
              <div className="space-y-2 p-4">
                <div className="flex items-center justify-between text-xs text-ink-muted">
                  <span>{shortDate(d.latest_progress_report.report_date)}</span>
                  <span className="font-mono">
                    {d.latest_progress_report.overall_progress_percent}%
                  </span>
                </div>
                <p className="line-clamp-4 text-sm text-ink-muted">
                  {d.latest_progress_report.narrative}
                </p>
                <div className="flex flex-wrap gap-2 text-[11px] text-ink-muted">
                  {d.latest_progress_report.weather_conditions && (
                    <span className="ec-badge bg-surface-muted text-ink-muted">
                      {d.latest_progress_report.weather_conditions}
                    </span>
                  )}
                  {d.latest_progress_report.workforce_count != null && (
                    <span className="ec-badge bg-surface-muted text-ink-muted">
                      {d.latest_progress_report.workforce_count} workers
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
