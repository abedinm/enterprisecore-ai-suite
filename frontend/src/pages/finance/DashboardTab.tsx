import { useQuery } from '@tanstack/react-query';
import { Download, Briefcase, Users, Truck, AlertTriangle } from 'lucide-react';
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { api } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/utils';

type Dashboard = {
  generated_at: string;
  period_start: string;
  period_end: string;
  kpis: {
    ytd_revenue: string; ytd_expenses: string; ytd_net: string;
    outstanding: string;
    active_customers: number; active_vendors: number;
    open_invoices: number; overdue_invoices: number;
    recurring_count: number;
  };
  revenue_by_month: { period: string; inflow: string; outflow: string; net: string }[];
  expenses_by_category: Record<string, string>;
  top_customers: { name: string; total: string }[];
  top_vendors: { name: string; total: string }[];
  upcoming_recurring: { id: string; title: string; amount: string; currency: string; cadence: string; next_due_date: string | null }[];
};

const PIE_COLORS = ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#a855f7', '#84cc16', '#ec4899'];

export function DashboardTab() {
  const { data, isLoading } = useQuery({
    queryKey: ['finance', 'dashboard'],
    queryFn: async () => (await api.get<Dashboard>('/finance/reports/dashboard')).data,
  });

  async function downloadPdf() {
    const r = await api.get('/finance/reports/dashboard/pdf', { responseType: 'blob' });
    const url = URL.createObjectURL(r.data as Blob);
    const a = document.createElement('a');
    a.href = url; a.download = `dashboard-${new Date().toISOString().slice(0, 10)}.pdf`; a.click();
    URL.revokeObjectURL(url);
  }

  if (isLoading || !data) {
    return <p className="text-sm text-ink-muted">Loading dashboard…</p>;
  }

  const flowData = data.revenue_by_month.map((e) => ({
    period: e.period, inflow: parseFloat(e.inflow), outflow: parseFloat(e.outflow), net: parseFloat(e.net),
  }));
  const catData = Object.entries(data.expenses_by_category).map(([name, value]) => ({
    name, value: parseFloat(value),
  })).filter((c) => c.value > 0);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Year to date</p>
          <p className="text-sm text-ink-muted">{formatDate(data.period_start)} → {formatDate(data.period_end)}</p>
        </div>
        <button className="ec-btn-primary" onClick={downloadPdf}><Download size={16} /> Export PDF</button>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <Kpi label="Revenue (YTD)" value={data.kpis.ytd_revenue} tone="positive" />
        <Kpi label="Expenses (YTD)" value={data.kpis.ytd_expenses} tone="negative" />
        <Kpi label="Net income (YTD)" value={data.kpis.ytd_net} tone="highlight" />
        <Kpi label="Outstanding receivables" value={data.kpis.outstanding} tone="warning" />
      </div>

      <div className="grid gap-3 md:grid-cols-5">
        <CountTile icon={Briefcase} label="Open invoices" value={data.kpis.open_invoices} />
        <CountTile icon={AlertTriangle} label="Overdue" value={data.kpis.overdue_invoices} highlight={data.kpis.overdue_invoices > 0} />
        <CountTile icon={Users} label="Customers" value={data.kpis.active_customers} />
        <CountTile icon={Truck} label="Vendors" value={data.kpis.active_vendors} />
        <CountTile icon={Briefcase} label="Recurring payments" value={data.kpis.recurring_count} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="ec-card p-5">
          <p className="mb-3 text-sm font-semibold">Cash inflow vs outflow (YTD)</p>
          <div className="h-72">
            {flowData.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={flowData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                  <XAxis dataKey="period" />
                  <YAxis />
                  <Tooltip formatter={(v) => formatCurrency(v as number)} />
                  <Legend />
                  <Area type="monotone" dataKey="inflow" stroke="#10b981" fill="#10b98133" />
                  <Area type="monotone" dataKey="outflow" stroke="#ef4444" fill="#ef444433" />
                </AreaChart>
              </ResponsiveContainer>
            ) : <EmptyChart text="No paid invoices or expenses yet" />}
          </div>
        </div>

        <div className="ec-card p-5">
          <p className="mb-3 text-sm font-semibold">Expenses by category</p>
          <div className="h-72">
            {catData.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={catData} dataKey="value" nameKey="name" outerRadius={90} label>
                    {catData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                  <Tooltip formatter={(v) => formatCurrency(v as number)} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : <EmptyChart text="No expenses recorded yet" />}
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <RankList title="Top customers (YTD)" rows={data.top_customers.map((c) => ({ label: c.name, value: c.total }))} />
        <RankList title="Top vendors (YTD)" rows={data.top_vendors.map((v) => ({ label: v.name, value: v.total }))} />
        <div className="ec-card p-5">
          <p className="mb-3 text-sm font-semibold">Upcoming recurring</p>
          {data.upcoming_recurring.length ? (
            <ul className="space-y-2 text-sm">
              {data.upcoming_recurring.map((r) => (
                <li key={r.id} className="flex justify-between rounded-md bg-surface-muted px-3 py-2">
                  <div>
                    <p className="font-medium">{r.title}</p>
                    <p className="text-xs text-ink-muted">{r.cadence} · due {formatDate(r.next_due_date)}</p>
                  </div>
                  <strong>{formatCurrency(r.amount, r.currency)}</strong>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-ink-muted">No upcoming recurring payments.</p>}
        </div>
      </div>

      <div className="ec-card p-5">
        <p className="mb-3 text-sm font-semibold">Net cash flow by month</p>
        <div className="h-56">
          {flowData.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={flowData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                <XAxis dataKey="period" />
                <YAxis />
                <Tooltip formatter={(v) => formatCurrency(v as number)} />
                <Bar dataKey="net" fill="#4f46e5" />
              </BarChart>
            </ResponsiveContainer>
          ) : <EmptyChart text="No data yet" />}
        </div>
      </div>
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone: 'positive' | 'negative' | 'highlight' | 'warning' }) {
  const cls = tone === 'positive' ? 'text-emerald-500'
    : tone === 'negative' ? 'text-rose-500'
    : tone === 'warning' ? 'text-amber-500'
    : 'text-brand-600';
  return (
    <div className="ec-card p-5">
      <p className="text-sm text-ink-muted">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${cls}`}>{formatCurrency(value)}</p>
    </div>
  );
}

function CountTile({ icon: Icon, label, value, highlight }: { icon: typeof Briefcase; label: string; value: number; highlight?: boolean }) {
  return (
    <div className={`ec-card p-4 ${highlight ? 'border-rose-500/40 bg-rose-500/5' : ''}`}>
      <div className="flex items-center justify-between">
        <Icon size={18} className={highlight ? 'text-rose-500' : 'text-ink-muted'} />
        <p className="text-2xl font-semibold">{value}</p>
      </div>
      <p className="mt-1 text-xs text-ink-muted">{label}</p>
    </div>
  );
}

function RankList({ title, rows }: { title: string; rows: { label: string; value: string }[] }) {
  return (
    <div className="ec-card p-5">
      <p className="mb-3 text-sm font-semibold">{title}</p>
      {rows.length ? (
        <ol className="space-y-2 text-sm">
          {rows.map((r, i) => (
            <li key={i} className="flex justify-between rounded-md bg-surface-muted px-3 py-2">
              <span>{i + 1}. {r.label}</span>
              <strong>{formatCurrency(r.value)}</strong>
            </li>
          ))}
        </ol>
      ) : <p className="text-sm text-ink-muted">No data yet.</p>}
    </div>
  );
}

function EmptyChart({ text }: { text: string }) {
  return <div className="grid h-full place-items-center text-sm text-ink-muted">{text}</div>;
}
