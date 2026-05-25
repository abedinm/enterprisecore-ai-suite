import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { ArrowDown, ArrowUp, Plus, Save, Trash2 } from 'lucide-react';
import { marketingApi, type MarketingNavItem } from '../../lib/marketing';

type Row = MarketingNavItem & { _local?: string };

export function MarketingNavigationPage() {
  const qc = useQueryClient();
  const stateQ = useQuery({
    queryKey: ['marketing', 'state'],
    queryFn: () => marketingApi.getState(),
  });

  const [rows, setRows] = useState<Row[]>([]);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (stateQ.data && !hydrated) {
      const sorted = [...stateQ.data.navigation].sort((a, b) => a.order - b.order);
      setRows(sorted);
      setHydrated(true);
    }
  }, [stateQ.data, hydrated]);

  const save = useMutation({
    mutationFn: () =>
      marketingApi.replaceNavigation(
        rows.map((r, idx) => ({
          id: r._local ? undefined : r.id,
          label: r.label,
          route: r.route,
          enabled: r.enabled,
          order: idx,
        })),
      ),
    onSuccess: (fresh) => {
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      setRows([...fresh].sort((a, b) => a.order - b.order));
      toast.success('Navigation saved');
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } }; message?: string })
        .response?.data?.detail ?? (err as Error).message ?? 'Failed to save';
      toast.error(typeof detail === 'string' ? detail : 'Failed to save');
    },
  });

  function update(idx: number, patch: Partial<Row>) {
    setRows((curr) => curr.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  }

  function move(idx: number, delta: number) {
    setRows((curr) => {
      const next = [...curr];
      const target = idx + delta;
      if (target < 0 || target >= next.length) return curr;
      [next[idx], next[target]] = [next[target], next[idx]];
      return next;
    });
  }

  function remove(idx: number) {
    setRows((curr) => curr.filter((_, i) => i !== idx));
  }

  function addRow() {
    setRows((curr) => [
      ...curr,
      {
        id: `tmp-${Date.now()}`,
        _local: 'new',
        label: 'New link',
        route: '/',
        enabled: true,
        order: curr.length,
      },
    ]);
  }

  if (stateQ.isLoading) {
    return <p className="text-sm text-ink-muted">Loading navigation…</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Site navigation</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Reorder, rename, and toggle the links shown in the public site header.
            Saving replaces the entire menu in one atomic write.
          </p>
        </div>
        <button type="button" className="ec-btn-secondary" onClick={addRow}>
          <Plus size={16} /> Add link
        </button>
      </div>

      <div className="ec-card overflow-hidden">
        {rows.length === 0 && (
          <p className="p-6 text-center text-sm text-ink-muted">
            No nav items. Add your first link to populate the header menu.
          </p>
        )}
        <ul>
          {rows.map((row, idx) => (
            <li
              key={row.id}
              className="grid grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)_auto_auto] items-center gap-2 border-b border-border/60 p-3 last:border-b-0"
            >
              <div className="flex flex-col">
                <button
                  type="button"
                  className="ec-btn-ghost !px-1 !py-0.5"
                  onClick={() => move(idx, -1)}
                  disabled={idx === 0}
                  title="Move up"
                >
                  <ArrowUp size={14} />
                </button>
                <button
                  type="button"
                  className="ec-btn-ghost !px-1 !py-0.5"
                  onClick={() => move(idx, +1)}
                  disabled={idx === rows.length - 1}
                  title="Move down"
                >
                  <ArrowDown size={14} />
                </button>
              </div>
              <input
                className="ec-input"
                placeholder="Label"
                value={row.label}
                onChange={(e) => update(idx, { label: e.target.value })}
              />
              <input
                className="ec-input font-mono text-xs"
                placeholder="/route"
                value={row.route}
                onChange={(e) => update(idx, { route: e.target.value })}
              />
              <label className="flex items-center gap-1.5 text-xs text-ink-muted">
                <input
                  type="checkbox"
                  checked={row.enabled}
                  onChange={(e) => update(idx, { enabled: e.target.checked })}
                />
                Enabled
              </label>
              <button
                type="button"
                className="ec-btn-ghost !px-2 !py-1.5 text-rose-600"
                onClick={() => remove(idx)}
                title="Remove"
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex justify-end gap-2">
        <button
          type="button"
          className="ec-btn-primary"
          onClick={() => save.mutate()}
          disabled={save.isPending}
        >
          <Save size={16} /> {save.isPending ? 'Saving…' : 'Save navigation'}
        </button>
      </div>
    </div>
  );
}
