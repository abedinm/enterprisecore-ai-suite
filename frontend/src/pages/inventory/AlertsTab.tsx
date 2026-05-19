import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { AlertTriangle, Check, RefreshCw, ShoppingCart } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';
import { Product, StockAlert, Supplier } from './types';

export function AlertsTab() {
  const qc = useQueryClient();
  const [showResolved, setShowResolved] = useState(false);

  const alerts = useQuery({
    queryKey: ['inventory', 'alerts', showResolved],
    queryFn: async () => (await api.get<StockAlert[]>('/inventory/alerts', {
      params: showResolved ? {} : { is_resolved: false },
    })).data,
  });

  const products = useQuery({
    queryKey: ['inventory', 'products'],
    queryFn: async () => (await api.get<Product[]>('/inventory/products')).data,
  });
  const suppliers = useQuery({
    queryKey: ['inventory', 'suppliers'],
    queryFn: async () => (await api.get<Supplier[]>('/inventory/suppliers')).data,
  });

  const resolve = useMutation({
    mutationFn: async (id: string) => (await api.post(`/inventory/alerts/${id}/resolve`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventory', 'alerts'] }),
  });

  const recompute = useMutation({
    mutationFn: async () => (await api.post('/inventory/alerts/recompute')).data,
    onSuccess: (data: any) => {
      toast.success(`Recomputed: ${data.created} new, ${data.resolved} resolved`);
      qc.invalidateQueries({ queryKey: ['inventory', 'alerts'] });
    },
  });

  const reorder = useMutation({
    mutationFn: async (productId: string) => {
      const product = products.data?.find((p) => p.id === productId);
      if (!product) throw new Error('Product not found');
      const qty = product.reorder_quantity || Math.max(product.low_stock_threshold * 2, 10);
      const today = new Date().toISOString().slice(0, 10);
      return (await api.post('/inventory/purchase-orders', {
        supplier_id: product.supplier_id, status: 'draft',
        order_date: today,
        notes: `Auto-reorder for low stock: ${product.name}`,
        lines: [{ product_id: productId, description: product.name, quantity: qty, unit_cost: product.unit_cost, received_quantity: 0 }],
      })).data;
    },
    onSuccess: () => { toast.success('Reorder PO created'); qc.invalidateQueries({ queryKey: ['inventory'] }); },
    onError: () => toast.error('Could not create PO'),
  });

  const grouped = (alerts.data ?? []).reduce<Record<string, StockAlert[]>>((acc, a) => {
    acc[a.alert_type] = acc[a.alert_type] || [];
    acc[a.alert_type].push(a);
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Low-Stock Alerts</p>
          <p className="text-sm text-ink-muted">{(alerts.data ?? []).filter((a) => !a.is_resolved).length} open alerts.</p>
        </div>
        <div className="flex items-end gap-2">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={showResolved} onChange={(e) => setShowResolved(e.target.checked)} /> Show resolved</label>
          <button className="ec-btn-secondary" disabled={recompute.isPending} onClick={() => recompute.mutate()}>
            <RefreshCw size={14} className={recompute.isPending ? 'animate-spin' : ''} /> Recompute
          </button>
        </div>
      </div>

      {Object.entries(grouped).map(([type, list]) => (
        <div key={type} className="ec-card overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border bg-surface-muted px-3 py-2 text-sm font-semibold">
            <AlertTriangle size={14} className={type === 'out_of_stock' ? 'text-rose-600' : 'text-amber-600'} />
            {type === 'out_of_stock' ? 'Out of stock' : 'Low stock'} ({list.length})
          </div>
          <table className="ec-table">
            <thead><tr><th>Product</th><th>Current</th><th>Threshold</th><th>Supplier</th><th>Detected</th><th></th></tr></thead>
            <tbody>
              {list.map((a) => {
                const product = products.data?.find((p) => p.id === a.product_id);
                const supplier = suppliers.data?.find((s) => s.id === product?.supplier_id);
                return (
                  <tr key={a.id} className={a.is_resolved ? 'opacity-50' : ''}>
                    <td className="font-medium">
                      <p>{product?.name ?? '—'}</p>
                      <p className="font-mono text-xs text-ink-muted">{product?.sku}</p>
                    </td>
                    <td className={a.current_qty <= 0 ? 'text-rose-600 font-semibold' : ''}>{a.current_qty}</td>
                    <td>{a.threshold}</td>
                    <td>{supplier?.name ?? '—'}</td>
                    <td className="text-xs text-ink-muted">{formatDateTime((a as any).created_at)}</td>
                    <td className="text-right whitespace-nowrap">
                      {!a.is_resolved && (
                        <>
                          {product && (
                            <button className="ec-btn-ghost" title="Auto-reorder" onClick={() => reorder.mutate(a.product_id)}><ShoppingCart size={14} /></button>
                          )}
                          <button className="ec-btn-ghost text-emerald-600" title="Mark resolved" onClick={() => resolve.mutate(a.id)}><Check size={14} /></button>
                        </>
                      )}
                      {a.is_resolved && <span className="text-xs text-emerald-600">resolved</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
      {Object.keys(grouped).length === 0 && <div className="ec-card p-10 text-center text-ink-muted">No alerts {showResolved ? 'in history' : '— stock is healthy'}.</div>}
    </div>
  );
}
