import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit3, X, Search, Image as ImgIcon } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';
import { formatCurrency } from '../../lib/utils';
import { Product, ProductCategory, Supplier } from './types';

export function CatalogTab() {
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [supplierId, setSupplierId] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Product | null>(null);
  const [showCategories, setShowCategories] = useState(false);

  const products = useQuery({
    queryKey: ['inventory', 'products', q, categoryId, supplierId],
    queryFn: async () => (await api.get<Product[]>('/inventory/products', {
      params: { ...(q ? { q } : {}), ...(categoryId ? { category_id: categoryId } : {}),
                ...(supplierId ? { supplier_id: supplierId } : {}) },
    })).data,
  });
  const categories = useQuery({
    queryKey: ['inventory', 'categories'],
    queryFn: async () => (await api.get<ProductCategory[]>('/inventory/categories')).data,
  });
  const suppliers = useQuery({
    queryKey: ['inventory', 'suppliers'],
    queryFn: async () => (await api.get<Supplier[]>('/inventory/suppliers')).data,
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/inventory/products/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventory', 'products'] }),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Product Catalog</p>
          <p className="text-sm text-ink-muted">{products.data?.length ?? 0} products.</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-subtle" />
            <input className="ec-input pl-8" placeholder="Search SKU, name, barcode" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className="ec-input" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">All categories</option>
            {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select className="ec-input" value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
            <option value="">All suppliers</option>
            {suppliers.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <button className="ec-btn-secondary" onClick={() => setShowCategories((v) => !v)}>Categories</button>
          <button className="ec-btn-primary" onClick={() => { setEditing(null); setShowForm(true); }}><Plus size={16} /> Add product</button>
        </div>
      </div>

      {showCategories && (
        <CategoriesPanel
          categories={categories.data ?? []}
          onChange={() => qc.invalidateQueries({ queryKey: ['inventory', 'categories'] })}
        />
      )}

      {(showForm || editing) && (
        <ProductForm
          editing={editing}
          categories={categories.data ?? []}
          suppliers={suppliers.data ?? []}
          onSaved={() => { setShowForm(false); setEditing(null); qc.invalidateQueries({ queryKey: ['inventory', 'products'] }); }}
          onCancel={() => { setShowForm(false); setEditing(null); }}
        />
      )}

      <div className="ec-card overflow-x-auto">
        <table className="ec-table">
          <thead>
            <tr><th>SKU</th><th>Name</th><th>Category</th><th>Supplier</th><th>Cost</th><th>Price</th><th>Threshold</th><th>UoM</th><th>Active</th><th></th></tr>
          </thead>
          <tbody>
            {products.data?.length ? products.data.map((p) => (
              <tr key={p.id}>
                <td className="font-mono text-xs">{p.sku}</td>
                <td className="font-medium">
                  <div className="flex items-center gap-2">
                    {p.image_url ? <img src={p.image_url} alt="" className="h-7 w-7 rounded object-cover" /> : <div className="grid h-7 w-7 place-items-center rounded bg-surface-muted text-ink-subtle"><ImgIcon size={12} /></div>}
                    {p.name}
                  </div>
                </td>
                <td>{categories.data?.find((c) => c.id === p.category_id)?.name ?? '—'}</td>
                <td>{suppliers.data?.find((s) => s.id === p.supplier_id)?.name ?? '—'}</td>
                <td>{formatCurrency(p.unit_cost)}</td>
                <td>{formatCurrency(p.unit_price)}</td>
                <td>{p.low_stock_threshold}</td>
                <td>{p.unit_of_measure}</td>
                <td>{p.is_active ? <span className="ec-badge-green">yes</span> : <span className="ec-badge">no</span>}</td>
                <td className="text-right whitespace-nowrap">
                  <button className="ec-btn-ghost" onClick={() => { setEditing(p); setShowForm(true); }}><Edit3 size={14} /></button>
                  <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete product?')) remove.mutate(p.id); }}><Trash2 size={14} /></button>
                </td>
              </tr>
            )) : <tr><td colSpan={10} className="py-10 text-center text-ink-muted">No products — add one to get started.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ProductForm({ editing, categories, suppliers, onSaved, onCancel }: {
  editing: Product | null; categories: ProductCategory[]; suppliers: Supplier[];
  onSaved: () => void; onCancel: () => void;
}) {
  const [sku, setSku] = useState(editing?.sku ?? '');
  const [name, setName] = useState(editing?.name ?? '');
  const [description, setDescription] = useState(editing?.description ?? '');
  const [categoryId, setCategoryId] = useState(editing?.category_id ?? '');
  const [supplierId, setSupplierId] = useState(editing?.supplier_id ?? '');
  const [unitCost, setUnitCost] = useState(editing?.unit_cost ?? '0');
  const [unitPrice, setUnitPrice] = useState(editing?.unit_price ?? '0');
  const [threshold, setThreshold] = useState(editing?.low_stock_threshold ?? 0);
  const [reorder, setReorder] = useState(editing?.reorder_quantity ?? 0);
  const [barcode, setBarcode] = useState(editing?.barcode ?? '');
  const [uom, setUom] = useState(editing?.unit_of_measure ?? 'ea');
  const [weight, setWeight] = useState(editing?.weight_kg ?? '0');
  const [imageUrl, setImageUrl] = useState(editing?.image_url ?? '');
  const [active, setActive] = useState(editing?.is_active ?? true);

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        sku, name, description, category_id: categoryId || null, supplier_id: supplierId || null,
        unit_cost: unitCost, unit_price: unitPrice, low_stock_threshold: threshold,
        reorder_quantity: reorder, barcode: barcode || null, barcode_type: editing?.barcode_type ?? 'code128',
        unit_of_measure: uom, weight_kg: weight, image_url: imageUrl || null, is_active: active,
      };
      if (editing) return (await api.patch(`/inventory/products/${editing.id}`, body)).data;
      return (await api.post('/inventory/products', body)).data;
    },
    onSuccess: () => { toast.success('Saved'); onSaved(); },
    onError: () => toast.error('Save failed'),
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? `Edit ${editing.sku}` : 'New product'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <div><label className="ec-label">SKU</label><input className="ec-input" value={sku} onChange={(e) => setSku(e.target.value)} /></div>
        <div className="md:col-span-2"><label className="ec-label">Name</label><input className="ec-input" value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div><label className="ec-label">Barcode</label><input className="ec-input" value={barcode ?? ''} onChange={(e) => setBarcode(e.target.value)} /></div>
        <div className="md:col-span-4"><label className="ec-label">Description</label><textarea className="ec-input" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} /></div>
        <div><label className="ec-label">Category</label>
          <select className="ec-input" value={categoryId ?? ''} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">—</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Supplier</label>
          <select className="ec-input" value={supplierId ?? ''} onChange={(e) => setSupplierId(e.target.value)}>
            <option value="">—</option>
            {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Unit cost</label><input type="number" className="ec-input" step="any" value={unitCost} onChange={(e) => setUnitCost(e.target.value)} /></div>
        <div><label className="ec-label">Unit price</label><input type="number" className="ec-input" step="any" value={unitPrice} onChange={(e) => setUnitPrice(e.target.value)} /></div>
        <div><label className="ec-label">Low stock threshold</label><input type="number" className="ec-input" value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} /></div>
        <div><label className="ec-label">Reorder qty</label><input type="number" className="ec-input" value={reorder} onChange={(e) => setReorder(Number(e.target.value))} /></div>
        <div><label className="ec-label">Unit of measure</label><input className="ec-input" value={uom} onChange={(e) => setUom(e.target.value)} placeholder="ea, kg, box" /></div>
        <div><label className="ec-label">Weight (kg)</label><input type="number" className="ec-input" step="any" value={weight} onChange={(e) => setWeight(e.target.value)} /></div>
        <div className="md:col-span-3"><label className="ec-label">Image URL</label><input className="ec-input" value={imageUrl ?? ''} onChange={(e) => setImageUrl(e.target.value)} placeholder="https://..." /></div>
        <div className="md:col-span-4"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Active</label></div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!sku || !name || save.isPending} onClick={() => save.mutate()}>{editing ? 'Save' : 'Create'}</button>
      </div>
    </div>
  );
}

function CategoriesPanel({ categories, onChange }: { categories: ProductCategory[]; onChange: () => void }) {
  const [name, setName] = useState('');
  const [parentId, setParentId] = useState('');
  const [description, setDescription] = useState('');

  const create = useMutation({
    mutationFn: async () => (await api.post('/inventory/categories', {
      name, parent_id: parentId || null, description,
    })).data,
    onSuccess: () => { setName(''); setDescription(''); toast.success('Category added'); onChange(); },
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/inventory/categories/${id}`)).data,
    onSuccess: () => { toast.success('Removed'); onChange(); },
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 space-y-3">
      <p className="text-sm font-semibold">Categories ({categories.length})</p>
      <div className="grid gap-2 md:grid-cols-[1fr_1fr_1fr_auto]">
        <input className="ec-input" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <select className="ec-input" value={parentId} onChange={(e) => setParentId(e.target.value)}>
          <option value="">Top-level</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <input className="ec-input" placeholder="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
        <button className="ec-btn-primary" disabled={!name || create.isPending} onClick={() => create.mutate()}>Add</button>
      </div>
      <table className="ec-table">
        <thead><tr><th>Name</th><th>Parent</th><th>Description</th><th></th></tr></thead>
        <tbody>
          {categories.length ? categories.map((c) => (
            <tr key={c.id}>
              <td className="font-medium">{c.name}</td>
              <td>{categories.find((p) => p.id === c.parent_id)?.name ?? '—'}</td>
              <td>{c.description}</td>
              <td className="text-right"><button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete category?')) remove.mutate(c.id); }}><Trash2 size={14} /></button></td>
            </tr>
          )) : <tr><td colSpan={4} className="py-4 text-center text-ink-muted">No categories yet.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
