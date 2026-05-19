import { useQuery } from '@tanstack/react-query';
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Users, Briefcase, Star, Award, AlertOctagon, CalendarOff, UserCheck, UserX } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency } from '../../lib/utils';

type Analytics = {
  headcount: number; active: number; on_leave: number;
  by_department: Record<string, number>;
  avg_salary: string;
  open_positions: number; candidates_in_pipeline: number;
  pending_leave_requests: number;
  by_status: Record<string, number>;
  hires_by_month: Record<string, number>;
  review_avg: string;
  training_completion_rate: string;
  disciplinary_count: number;
};

const PIE_COLORS = ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#a855f7', '#84cc16', '#ec4899'];

export function HRAnalyticsTab() {
  const { data, isLoading } = useQuery({
    queryKey: ['hr', 'analytics'],
    queryFn: async () => (await api.get<Analytics>('/hr/analytics')).data,
  });

  if (isLoading || !data) return <p className="text-sm text-ink-muted">Loading analytics…</p>;

  const deptData = Object.entries(data.by_department).map(([name, value]) => ({ name, value }));
  const statusData = Object.entries(data.by_status).map(([name, value]) => ({ name, value }));
  const hiresData = Object.entries(data.hires_by_month).map(([period, count]) => ({ period, count }));

  return (
    <div className="space-y-5">
      <div>
        <p className="text-xs uppercase tracking-wider text-ink-muted">HR analytics</p>
        <p className="text-sm text-ink-muted">Live snapshot of headcount, hiring, leave, training and performance.</p>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <Kpi icon={Users} label="Headcount" value={data.headcount.toString()} />
        <Kpi icon={UserCheck} label="Active" value={data.active.toString()} tone="positive" />
        <Kpi icon={UserX} label="On leave" value={data.on_leave.toString()} tone="warning" />
        <Kpi icon={Briefcase} label="Avg salary" value={formatCurrency(data.avg_salary)} />
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <Kpi icon={Briefcase} label="Open positions" value={data.open_positions.toString()} />
        <Kpi icon={Users} label="Candidate pipeline" value={data.candidates_in_pipeline.toString()} />
        <Kpi icon={CalendarOff} label="Pending leave" value={data.pending_leave_requests.toString()} tone="warning" />
        <Kpi icon={AlertOctagon} label="Disciplinary" value={data.disciplinary_count.toString()} tone={data.disciplinary_count > 0 ? 'negative' : undefined} />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <Kpi icon={Star} label="Avg review score" value={`${parseFloat(data.review_avg).toFixed(2)} / 5`} />
        <Kpi icon={Award} label="Training completion" value={`${(parseFloat(data.training_completion_rate) * 100).toFixed(0)}%`} tone="positive" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="ec-card p-5">
          <p className="mb-3 text-sm font-semibold">Headcount by department</p>
          <div className="h-64">
            {deptData.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={deptData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                  <XAxis dataKey="name" />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="value" fill="#4f46e5" />
                </BarChart>
              </ResponsiveContainer>
            ) : <Empty />}
          </div>
        </div>

        <div className="ec-card p-5">
          <p className="mb-3 text-sm font-semibold">Status mix</p>
          <div className="h-64">
            {statusData.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={statusData} dataKey="value" nameKey="name" outerRadius={90} label>
                    {statusData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : <Empty />}
          </div>
        </div>
      </div>

      <div className="ec-card p-5">
        <p className="mb-3 text-sm font-semibold">Hires per month</p>
        <div className="h-64">
          {hiresData.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={hiresData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                <XAxis dataKey="period" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Line type="monotone" dataKey="count" stroke="#10b981" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          ) : <Empty />}
        </div>
      </div>
    </div>
  );
}

function Kpi({ icon: Icon, label, value, tone }: { icon: typeof Users; label: string; value: string; tone?: 'positive' | 'negative' | 'warning' }) {
  const cls = tone === 'positive' ? 'text-emerald-500'
    : tone === 'negative' ? 'text-rose-500'
    : tone === 'warning' ? 'text-amber-500' : '';
  return (
    <div className="ec-card p-4">
      <div className="flex items-center justify-between">
        <Icon size={18} className="text-ink-muted" />
        <p className={`text-2xl font-semibold ${cls}`}>{value}</p>
      </div>
      <p className="mt-1 text-xs text-ink-muted">{label}</p>
    </div>
  );
}

function Empty() {
  return <div className="grid h-full place-items-center text-sm text-ink-muted">No data yet</div>;
}
