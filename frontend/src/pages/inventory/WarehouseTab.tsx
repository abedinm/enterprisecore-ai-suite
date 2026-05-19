import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit3, X, Warehouse as WarehouseIcon, Layers } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';
import { Warehouse, WarehouseZone } from './types';

export function WarehouseTab() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Warehouse | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const warehouses = useQuery({
    queryKey: ['inventory', 'warehouses'],
    queryFn: async () => (await api.get<Warehouse[]>('/inventory/warehouses')).data,
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/inventory/warehouses/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventory', 'warehouses'] }),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Warehouse Organizer</p>
          <p className="text-sm text-ink-muted">{warehouses.data?.length ?? 0} locations with zone breakdown.</p>
        </div>
        <button className="ec-btn-primary" onClick={() => { setEditing(null); setShowForm(true); }}><Plus size={16} /> New warehouse</button>
      </div>

      {(showForm || editing) && (
        <WarehouseForm
          editing={editing}
          onSaved={() => { setShowForm(false); setEditing(null); qc.invalidateQueries({ queryKey: ['inventory', 'warehouses'] }); }}
          onCancel={() => { setShowForm(false); setEditing(null); }}
        />
      )}

      <div className="grid gap-3 lg:grid-cols-[1fr_1.4fr]">
        <div className="ec-card overflow-y-auto">
          <div className="border-b border-border bg-surface-muted px-3 py-2 text-sm font-semibold">Warehouses</div>
          <div className="divide-y divide-border/60">
            {warehouses.data?.length ? warehouses.data.map((w) => (
              <button
                key={w.id}
                onClick={() => setSelected(w.id)}
                className={`flex w-full items-start justify-between p-3 text-left transition hover:bg-surface-muted ${selected === w.id ? 'bg-surface-muted' : ''}`}
              >
                <div className="flex items-start gap-2">
                  <WarehouseIcon size={16} className="mt-0.5 shrink-0 text-brand-600" />
                  <div>
                    <p className="font-medium">{w.name} {w.code && <span className="text-xs text-ink-muted">({w.code})</span>}</p>
                    {w.address && <p className="text-xs text-ink-muted">{w.address}</p>}
                    {w.manager && <p className="text-xs">{w.manager} · {w.phone ?? '—'}</p>}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <span className="text-xs text-ink-muted">{w.capacity}cap</span>
                  <span>{w.is_active ? <span className="ec-badge-green">active</span> : <span className="ec-badge">inactive</span>}</span>
                </div>
              </button>
            )) : <p className="p-6 text-center text-sm text-ink-muted">No warehouses yet.</p>}
          </div>
        </div>

        {selected ? (
          <WarehouseDetail
            warehouse={warehouses.data?.find((w) => w.id === selected) ?? null}
            onEdit={() => { setEditing(warehouses.data?.find((w) => w.id === selected) ?? null); setShowForm(true); }}
            onDelete={(id) => { if (confirm('Delete warehouse and zones?')) remove.mutate(id); }}
          />
        ) : (
          <div className="ec-card p-6 text-center text-sm text-ink-muted">Select a warehouse to manage zones and view inventory.</div>
        )}
      </div>
    </div>
  );
}

function WarehouseForm({ editing, onSaved, onCancel }: { editing: Warehouse | null; onSaved: () => void; onCancel: () => void }) {
  const [name, setName] = useState(editing?.name ?? '');
  const [code, setCode] = useState(editing?.code ?? '');
  const [address, setAddress] = useState(editing?.address ?? '');
  const [manager, setManager] = useState(editing?.manager ?? '');
  const [phone, setPhone] = useState(editing?.phone ?? '');
  const [capacity, setCapacity] = useState(editing?.capacity ?? 0);
  const [active, setActive] = useState(editing?.is_active ?? true);

  const save = useMutation({
    mutationFn: async () => {
      const body = { name, code, address: address || null, manager: manager || null, phone: phone || null, capacity, is_active: active };
      if (editing) return (await api.patch(`/inventory/warehouses/${editing.id}`, body)).data;
      return (await api.post('/inventory/warehouses', body)).data;
    },
    onSuccess: () => { toast.success('Saved'); onSaved(); },
    onError: () => toast.error('Save failed'),
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? 'Edit warehouse' : 'New warehouse'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div className="md:col-span-2"><label className="ec-label">Name</label><input className="ec-input" value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div><label className="ec-label">Code</label><input className="ec-input" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="WH-01" /></div>
        <div className="md:col-span-3"><label className="ec-label">Address</label><textarea className="ec-input" rows={2} value={address ?? ''} onChange={(e) => setAddress(e.target.value)} /></div>
        <div><label className="ec-label">Manager</label><input className="ec-input" value={manager ?? ''} onChange={(e) => setManager(e.target.value)} /></div>
        <div><label className="ec-label">Phone</label><input className="ec-input" value={phone ?? ''} onChange={(e) => setPhone(e.target.value)} /></div>
        <div><label className="ec-label">Capacity (units)</label><input type="number" className="ec-input" value={capacity} onChange={(e) => setCapacity(Number(e.target.value))} /></div>
        <div className="md:col-span-3"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Active</label></div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!name || save.isPending} onClick={() => save.mutate()}>{editing ? 'Save' : 'Create'}</button>
      </div>
    </div>
  );
}

function WarehouseDetail({ warehouse, onEdit, onDelete }: { warehouse: Warehouse | null; onEdit: () => void; onDelete: (id: string) => void }) {
  const qc = useQueryClient();
  const [zoneName, setZoneName] = useState('');
  const [aisle, setAisle] = useState('');
  const [rack, setRack] = useState('');
  const [bin, setBin] = useState('');
  const [zoneCap, setZoneCap] = useState(0);

  const zones = useQuery({
    queryKey: ['inventory', 'zones', warehouse?.id],
    queryFn: async () => warehouse ? (await api.get<WarehouseZone[]>(`/inventory/warehouses/${warehouse.id}/zones`)).data : [],
    enabled: !!warehouse,
  });

  const inventory = useQuery({
    queryKey: ['inventory', 'wh-inventory', warehouse?.id],
    queryFn: async () => warehouse ? (await api.get<{ items: any[] }>(`/inventory/warehouses/${warehouse.id}/inventory`)).data : { items: [] },
    enabled: !!warehouse,
  });

  const createZone = useMutation({
    mutationFn: async () => warehouse ? (await api.post(`/inventory/warehouses/${warehouse.id}/zones`, {
      warehouse_id: warehouse.id, name: zoneName, aisle, rack, bin, capacity: zoneCap,
    })).data : null,
    onSuccess: () => {
      setZoneName(''); setAisle(''); setRack(''); setBin(''); setZoneCap(0);
      qc.invalidateQueries({ queryKey: ['inventory', 'zones'] });
    },
  });

  const removeZone = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/inventory/zones/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventory', 'zones'] }),
  });

  if (!warehouse) return null;
  return (
    <div className="space-y-3">
      <div className="ec-card p-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold">{warehouse.name}</h3>
            <p className="text-xs text-ink-muted">{warehouse.address ?? 'No address'}</p>
          </div>
          <div className="flex gap-1">
            <button className="ec-btn-ghost" onClick={onEdit}><Edit3 size={14} /></button>
            <button className="ec-btn-ghost text-rose-600" onClick={() => onDelete(warehouse.id)}><Trash2 size={14} /></button>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3 text-sm">
          <div><p className="text-xs text-ink-muted">Manager</p><p>{warehouse.manager ?? '—'}</p></div>
          <div><p className="text-xs text-ink-muted">Capacity</p><p>{warehouse.capacity} units</p></div>
          <div><p className="text-xs text-ink-muted">Phone</p><p>{warehouse.phone ?? '—'}</p></div>
        </div>
      </div>

      <div className="ec-card p-4">
        <div className="mb-3 flex items-center gap-2">
          <Layers size={14} className="text-brand-600" />
          <p className="text-sm font-semibold">Zones ({zones.data?.length ?? 0})</p>
        </div>
        <div className="grid gap-2 md:grid-cols-[1fr_60px_60px_60px_80px_auto]">
          <input className="ec-input" placeholder="Zone name" value={zoneName} onChange={(e) => setZoneName(e.target.value)} />
          <input className="ec-input" placeholder="Aisle" value={aisle} onChange={(e) => setAisle(e.target.value)} />
          <input className="ec-input" placeholder="Rack" value={rack} onChange={(e) => setRack(e.target.value)} />
          <input className="ec-input" placeholder="Bin" value={bin} onChange={(e) => setBin(e.target.value)} />
          <input type="number" className="ec-input" placeholder="Cap" value={zoneCap} onChange={(e) => setZoneCap(Number(e.target.value))} />
          <button className="ec-btn-primary" disabled={!zoneName || createZone.isPending} onClick={() => createZone.mutate()}><Plus size={14} /></button>
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="ec-table">
            <thead><tr><th>Name</th><th>Location</th><th>Capacity</th><th></th></tr></thead>
            <tbody>
              {zones.data?.length ? zones.data.map((z) => (
                <tr key={z.id}>
                  <td className="font-medium">{z.name}</td>
                  <td className="text-xs">A{z.aisle || '-'} · R{z.rack || '-'} · B{z.bin || '-'}</td>
                  <td>{z.capacity}</td>
                  <td className="text-right"><button className="ec-btn-ghost text-rose-600" onClick={() => removeZone.mutate(z.id)}><Trash2 size={14} /></button></td>
                </tr>
              )) : <tr><td colSpan={4} className="py-4 text-center text-xs text-ink-muted">No zones defined.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <div className="ec-card overflow-hidden">
        <div className="border-b border-border bg-surface-muted px-3 py-2 text-sm font-semibold">Inventory in this warehouse</div>
        <div className="max-h-64 overflow-y-auto">
          <table className="ec-table">
            <thead><tr><th>Product</th><th>SKU</th><th>Zone</th><th>Quantity</th></tr></thead>
            <tbody>
              {inventory.data?.items?.length ? inventory.data.items.map((i: any, idx: number) => (
                <tr key={idx}>
                  <td className="font-medium">{i.product_name}</td>
                  <td className="font-mono text-xs">{i.sku}</td>
                  <td>{i.zone_name}</td>
                  <td className="tabular-nums">{i.quantity}</td>
                </tr>
              )) : <tr><td colSpan={4} className="py-6 text-center text-xs text-ink-muted">No stock in this warehouse yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
