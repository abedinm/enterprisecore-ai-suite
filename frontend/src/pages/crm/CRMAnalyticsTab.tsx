import { useQuery } from '@tanstack/react-query';
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts';
import { TrendingUp, Workflow, Target, Phone, Trophy, X as XIcon } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency } from '../../lib/utils';

type Analytics = {
  pipeline_value: string;
  weighted_pipeline: string;
  deals_by_stage: Record<string, number>;
  won_value: string;
  lost_value: string;
  lead_count_by_status: Record<string, number>;
  open_follow_ups: number;
};

const PIE_COLORS = ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#a855f7'];

export function CRMAnalyticsTab() {
  const { data, isLoading } = useQuery({
    queryKey: ['crm', 'analytics'],
    queryFn: async () => (await api.get<Analytics>('/crm/analytics')).data,
  });

  if (isLoading || !data) return <p className="text-sm text-ink-muted">Loading…</p>;

  const stagesData = Object.entries(data.deals_by_stage).map(([name, value]) => ({ name, value }));
  const leadsData = Object.entries(data.lead_count_by_status).map(([name, value]) => ({ name, value }));
  const totalDeals = stagesData.reduce((s, x) => s + x.value, 0);
  const totalLeads = leadsData.reduce((s, x) => s + x.value, 0);
  const winRate = (parseFloat(data.won_value) + parseFloat(data.lost_value)) > 0
    ? (parseFloat(data.won_value) / (parseFloat(data.won_value) + parseFloat(data.lost_value))) * 100
    : 0;

  return (
    <div className="space-y-5">
      <div>
        <p className="text-xs uppercase tracking-wider text-ink-muted">CRM analytics</p>
        <p className="text-sm text-ink-muted">Live pipeline value, weighted forecast, win/loss, follow-ups.</p>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <Kpi icon={Workflow} label="Open pipeline" value={formatCurrency(data.pipeline_value)} />
        <Kpi icon={TrendingUp} label="Weighted forecast" value={formatCurrency(data.weighted_pipeline)} tone="highlight" />
        <Kpi icon={Trophy} label="Won (closed)" value={formatCurrency(data.won_value)} tone="positive" />
        <Kpi icon={XIcon} label="Lost" value={formatCurrency(data.lost_value)} tone="negative" />
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <Kpi icon={Target} label="Total leads" value={totalLeads.toString()} />
        <Kpi icon={Workflow} label="Total deals" value={totalDeals.toString()} />
        <Kpi icon={Phone} label="Open follow-ups" value={data.open_follow_ups.toString()} tone={data.open_follow_ups > 5 ? 'warning' : undefined} />
        <Kpi icon={Trophy} label="Win rate" value={`${winRate.toFixed(1)}%`} tone={winRate >= 50 ? 'positive' : 'warning'} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="ec-card p-5">
          <p className="mb-3 text-sm font-semibold">Deals by stage</p>
          <div className="h-64">
            {stagesData.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={stagesData}>
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
          <p className="mb-3 text-sm font-semibold">Leads by status</p>
          <div className="h-64">
            {leadsData.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={leadsData} dataKey="value" nameKey="name" outerRadius={90} label>
                    {leadsData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : <Empty />}
          </div>
        </div>
      </div>
    </div>
  );
}

function Kpi({ icon: Icon, label, value, tone }: { icon: typeof TrendingUp; label: string; value: string; tone?: 'positive' | 'negative' | 'highlight' | 'warning' }) {
  const cls = tone === 'positive' ? 'text-emerald-500'
    : tone === 'negative' ? 'text-rose-500'
    : tone === 'highlight' ? 'text-brand-600'
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
