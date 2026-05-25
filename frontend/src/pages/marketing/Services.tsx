import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { ArrowDown, ArrowUp, Edit3, Plus, Star, Trash2, X } from 'lucide-react';
import { marketingApi, type MarketingService, type ServiceInput } from '../../lib/marketing';

const EMPTY: ServiceInput = {
  icon: 'Sparkles',
  title: '',
  summary: '',
  details: '',
  price: '',
  featured: false,
  order: 0,
};

export function MarketingServicesPage() {
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['marketing', 'services'],
    queryFn: () => marketingApi.listServices(),
  });

  const sorted = useMemo(
    () => [...(listQ.data ?? [])].sort((a, b) => a.order - b.order),
    [listQ.data],
  );

  const [editing, setEditing] = useState<MarketingService | null>(null);
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => marketingApi.deleteService(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'services'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      toast.success('Service deleted');
    },
  });

  const reorder = useMutation({
    mutationFn: (order: { id: string; order: number }[]) =>
      marketingApi.reorderServices(order),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['marketing', 'services'] }),
  });

  function move(idx: number, delta: number) {
    const target = idx + delta;
    if (target < 0 || target >= sorted.length) return;
    const next = [...sorted];
    [next[idx], next[target]] = [next[target], next[idx]];
    reorder.mutate(next.map((s, i) => ({ id: s.id, order: i })));
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Services</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Service offerings shown in the services section and on /services.
          </p>
        </div>
        <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
          <Plus size={16} /> New service
        </button>
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading services…</p>}

      <div className="ec-card overflow-hidden">
        {sorted.length === 0 && !listQ.isLoading && (
          <p className="p-6 text-center text-sm text-ink-muted">
            No services yet. Add your first one to populate the services grid.
          </p>
        )}
        <ul>
          {sorted.map((svc, idx) => (
            <li
              key={svc.id}
              className="grid grid-cols-[auto_minmax(0,1fr)_auto_auto_auto] items-center gap-3 border-b border-border/60 p-3 last:border-b-0"
            >
              <div className="flex flex-col">
                <button
                  type="button"
                  className="ec-btn-ghost !px-1 !py-0.5"
                  onClick={() => move(idx, -1)}
                  disabled={idx === 0}
                >
                  <ArrowUp size={14} />
                </button>
                <button
                  type="button"
                  className="ec-btn-ghost !px-1 !py-0.5"
                  onClick={() => move(idx, +1)}
                  disabled={idx === sorted.length - 1}
                >
                  <ArrowDown size={14} />
                </button>
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  {svc.featured && (
                    <span className="ec-badge-amber inline-flex items-center gap-1">
                      <Star size={11} /> Featured
                    </span>
                  )}
                  <p className="truncate font-medium">{svc.title || <span className="italic text-ink-muted">Untitled</span>}</p>
                </div>
                {svc.summary && <p className="mt-0.5 line-clamp-1 text-xs text-ink-muted">{svc.summary}</p>}
              </div>
              <span className="text-xs text-ink-muted">{svc.price || '—'}</span>
              <button
                type="button"
                className="ec-btn-secondary !py-1.5 !px-2.5 text-xs"
                onClick={() => setEditing(svc)}
              >
                <Edit3 size={13} /> Edit
              </button>
              <button
                type="button"
                className="ec-btn-ghost !px-2 !py-1.5 text-rose-600"
                onClick={() => {
                  if (confirm(`Delete service "${svc.title}"?`)) remove.mutate(svc.id);
                }}
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      </div>

      {editing && (
        <ServiceModal
          initial={editing}
          isNew={false}
          onClose={() => setEditing(null)}
        />
      )}
      {creating && (
        <ServiceModal
          initial={{ ...EMPTY, order: sorted.length }}
          isNew
          onClose={() => setCreating(false)}
        />
      )}
    </div>
  );
}

function ServiceModal({
  initial,
  isNew,
  onClose,
}: {
  initial: ServiceInput & { id?: string };
  isNew: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<ServiceInput>({
    icon: initial.icon,
    title: initial.title,
    summary: initial.summary,
    details: initial.details,
    price: initial.price,
    featured: initial.featured,
    order: initial.order,
  });

  const save = useMutation({
    mutationFn: async () => {
      if (isNew) return marketingApi.createService(form);
      return marketingApi.updateService(initial.id!, form);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'services'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      toast.success(isNew ? 'Service added' : 'Service saved');
      onClose();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } }; message?: string })
        .response?.data?.detail ?? (err as Error).message ?? 'Failed to save';
      toast.error(typeof detail === 'string' ? detail : 'Failed to save');
    },
  });

  function update<K extends keyof ServiceInput>(key: K, value: ServiceInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-xl overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold">{isNew ? 'New service' : 'Edit service'}</p>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <form
          className="space-y-3 p-5"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="ec-label">Title</label>
              <input
                className="ec-input"
                required
                value={form.title}
                onChange={(e) => update('title', e.target.value)}
              />
            </div>
            <div>
              <label className="ec-label">Price</label>
              <input
                className="ec-input"
                value={form.price}
                onChange={(e) => update('price', e.target.value)}
                placeholder="From $5k"
              />
            </div>
            <div className="md:col-span-2">
              <label className="ec-label">Icon (lucide name)</label>
              <input
                className="ec-input font-mono"
                value={form.icon}
                onChange={(e) => update('icon', e.target.value)}
                placeholder="Sparkles"
              />
            </div>
            <div className="md:col-span-2">
              <label className="ec-label">Summary</label>
              <textarea
                className="ec-input min-h-[60px]"
                value={form.summary}
                onChange={(e) => update('summary', e.target.value)}
              />
            </div>
            <div className="md:col-span-2">
              <label className="ec-label">Details (markdown)</label>
              <textarea
                className="ec-input min-h-[120px] font-mono text-xs"
                value={form.details}
                onChange={(e) => update('details', e.target.value)}
              />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.featured}
              onChange={(e) => update('featured', e.target.checked)}
            />
            Featured — highlight in the services grid
          </label>
        </form>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="ec-btn-primary"
            disabled={save.isPending || !form.title.trim()}
            onClick={() => save.mutate()}
          >
            {save.isPending ? 'Saving…' : isNew ? 'Add service' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
