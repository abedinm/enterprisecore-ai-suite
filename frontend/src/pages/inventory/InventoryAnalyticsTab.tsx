import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid,
  PieChart, Pie, Cell, Legend,
} from 'recharts';
import { AlertTriangle, Boxes, DollarSign, Package, ShoppingCart, Truck, Users, RotateCcw } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency } from '../../lib/utils';

type Analytics = {
  total_products: number;
  active_products: number;
  low_stock_count: number;
  out_of_stock_count: number;
  low_stock_items: { product_id: string; sku: string; name: string; on_hand: number; threshold: number; status?: string }[];
  total_stock_value: string;
  open_purchase_orders: number;
  pending_shipments: number;
  pending_returns: number;
  total_warehouses: number;
  total_suppliers: number;
  movements_last_30_days: number;
  top_products: { id: string; sku: string; name: string; on_hand: number; value: number }[];
  movements_by_type: Record<string, number>;
  inventory_turnover: number;
  refund_total: string;
};

const TYPE_COLORS = ['#10b981', '#f43f5e', '#fbbf24', '#60a5fa'];

export function InventoryAnalyticsTab() {
  const data = useQuery({
    queryKey: ['inventory', 'analytics'],
    queryFn: async () => (await api.get<Analytics>('/inventory/analytics')).data,
  });

  const a = data.data;
  if (!a) return <p className="py-10 text-center text-ink-muted">Loading analytics…</p>;

  const movementData = Object.entries(a.movements_by_type).map(([name, value]) => ({ name, value }));
  const top = a.top_products.slice(0, 8).map((p) => ({ name: p.name.slice(0, 14), value: p.value }));

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-4">
        <StatCard icon={Package} label="Active products" value={a.active_products} sub={`${a.total_products} total`} />
        <StatCard icon={DollarSign} label="Stock value" value={formatCurrency(a.total_stock_value)} sub={`turnover ${a.inventory_turnover}%`} />
        <StatCard icon={AlertTriangle} label="Low stock" value={a.low_stock_count + a.out_of_stock_count} sub={`${a.out_of_stock_count} out`} alert={a.out_of_stock_count > 0} />
        <StatCard icon={Boxes} label="Movements (30d)" value={a.movements_last_30_days} />
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <StatCard icon={ShoppingCart} label="Open POs" value={a.open_purchase_orders} />
        <StatCard icon={Truck} label="Pending shipments" value={a.pending_shipments} />
        <StatCard icon={RotateCcw} label="Pending returns" value={a.pending_returns} sub={`${formatCurrency(a.refund_total)} refunded total`} />
        <StatCard icon={Users} label="Suppliers / Warehouses" value={`${a.total_suppliers} / ${a.total_warehouses}`} />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="ec-card p-4">
          <p className="mb-2 text-sm font-semibold">Stock movements (all time)</p>
          {movementData.length > 0 ? (
            <div className="h-56">
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={movementData} dataKey="value" nameKey="name" outerRadius={80} label>
                    {movementData.map((_, i) => <Cell key={i} fill={TYPE_COLORS[i % TYPE_COLORS.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={{ background: 'rgb(var(--color-surface-elevated))', border: '1px solid rgb(var(--color-border))' }} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="py-8 text-center text-xs text-ink-muted">No movements recorded yet.</p>
          )}
        </div>

        <div className="ec-card p-4">
          <p className="mb-2 text-sm font-semibold">Top products by stock value</p>
          {top.length > 0 ? (
            <div className="h-56">
              <ResponsiveContainer>
                <BarChart data={top} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                  <XAxis type="number" tick={{ fontSize: 10 }} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={90} />
                  <Tooltip formatter={(v: any) => formatCurrency(v)} contentStyle={{ background: 'rgb(var(--color-surface-elevated))', border: '1px solid rgb(var(--color-border))' }} />
                  <Bar dataKey="value" fill="#4f46e5" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="py-8 text-center text-xs text-ink-muted">No stock value to chart.</p>
          )}
        </div>
      </div>

      <div className="ec-card overflow-x-auto">
        <div className="border-b border-border bg-surface-muted px-3 py-2 text-sm font-semibold">Stock attention list ({a.low_stock_items.length})</div>
        <table className="ec-table">
          <thead><tr><th>SKU</th><th>Product</th><th>On hand</th><th>Threshold</th><th>Status</th></tr></thead>
          <tbody>
            {a.low_stock_items.length ? a.low_stock_items.map((i) => (
              <tr key={i.product_id}>
                <td className="font-mono text-xs">{i.sku}</td>
                <td className="font-medium">{i.name}</td>
                <td className={i.on_hand <= 0 ? 'text-rose-600 font-semibold' : 'text-amber-600'}>{i.on_hand}</td>
                <td>{i.threshold}</td>
                <td>
                  {i.on_hand <= 0 ? <span className="ec-badge-rose">out</span> : <span className="ec-badge-amber">low</span>}
                </td>
              </tr>
            )) : <tr><td colSpan={5} className="py-6 text-center text-ink-muted">All stock above threshold.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, sub, alert }: {
  icon: typeof Package; label: string; value: string | number; sub?: string; alert?: boolean;
}) {
  return (
    <div className={`ec-card p-3 ${alert ? 'ring-2 ring-rose-200 dark:ring-rose-900/40' : ''}`}>
      <div className="flex items-center gap-2">
        <Icon size={16} className={alert ? 'text-rose-600' : 'text-brand-600'} />
        <p className="text-[10px] uppercase tracking-wider text-ink-muted">{label}</p>
      </div>
      <p className={`mt-1 text-2xl font-semibold ${alert ? 'text-rose-600' : ''}`}>{value}</p>
      {sub && <p className="text-xs text-ink-muted">{sub}</p>}
    </div>
  );
}
