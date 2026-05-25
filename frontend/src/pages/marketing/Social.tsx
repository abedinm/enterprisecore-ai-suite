import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  ArrowDown,
  ArrowUp,
  Edit3,
  ExternalLink,
  Plus,
  Share2,
  Trash2,
  X,
} from 'lucide-react';
import {
  marketingApi,
  SOCIAL_PLATFORM_OPTIONS,
  type MarketingSocialLink,
  type SocialLinkInput,
} from '../../lib/marketing';

const EMPTY: SocialLinkInput = {
  platform: 'twitter',
  label: '',
  url: '',
  order: 0,
};

function platformLabel(value: string): string {
  return SOCIAL_PLATFORM_OPTIONS.find((p) => p.value === value)?.label ?? value;
}

export function MarketingSocialPage() {
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['marketing', 'social'],
    queryFn: () => marketingApi.listSocial(),
  });

  const sorted = useMemo(
    () => [...(listQ.data ?? [])].sort((a, b) => a.order - b.order),
    [listQ.data],
  );

  const [editing, setEditing] = useState<MarketingSocialLink | null>(null);
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => marketingApi.deleteSocial(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'social'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      toast.success('Link removed');
    },
  });

  const reorder = useMutation({
    mutationFn: (order: { id: string; order: number }[]) =>
      marketingApi.reorderSocial(order),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['marketing', 'social'] }),
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
          <h2 className="text-lg font-semibold">Social links</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Social profiles rendered in the footer and contact section.
          </p>
        </div>
        <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
          <Plus size={16} /> Add link
        </button>
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}

      {sorted.length === 0 && !listQ.isLoading && (
        <div className="grid place-items-center rounded-xl border border-dashed border-border bg-surface-muted/40 p-10 text-center">
          <Share2 size={28} className="mb-3 text-ink-subtle" />
          <p className="font-semibold">No social links yet</p>
        </div>
      )}

      <div className="ec-card overflow-hidden">
        <ul>
          {sorted.map((s, idx) => (
            <li
              key={s.id}
              className="grid grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)_auto_auto_auto] items-center gap-3 border-b border-border/60 p-3 last:border-b-0"
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
                <p className="font-medium">{s.label || platformLabel(s.platform)}</p>
                <p className="text-xs text-ink-muted">{platformLabel(s.platform)}</p>
              </div>
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex min-w-0 items-center gap-1 truncate font-mono text-xs text-brand-600 hover:underline"
              >
                <ExternalLink size={12} className="shrink-0" />
                <span className="truncate">{s.url}</span>
              </a>
              <span className="text-xs text-ink-subtle">#{idx + 1}</span>
              <button
                type="button"
                className="ec-btn-secondary !py-1.5 !px-2.5 text-xs"
                onClick={() => setEditing(s)}
              >
                <Edit3 size={13} />
              </button>
              <button
                type="button"
                className="ec-btn-ghost !px-2 !py-1.5 text-rose-600"
                onClick={() => {
                  if (confirm(`Remove link to ${platformLabel(s.platform)}?`)) remove.mutate(s.id);
                }}
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      </div>

      {editing && (
        <SocialModal initial={editing} isNew={false} onClose={() => setEditing(null)} />
      )}
      {creating && (
        <SocialModal
          initial={{ ...EMPTY, order: sorted.length }}
          isNew
          onClose={() => setCreating(false)}
        />
      )}
    </div>
  );
}

function SocialModal({
  initial,
  isNew,
  onClose,
}: {
  initial: SocialLinkInput & { id?: string };
  isNew: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<SocialLinkInput>({
    platform: initial.platform,
    label: initial.label,
    url: initial.url,
    order: initial.order,
  });

  const save = useMutation({
    mutationFn: () =>
      isNew
        ? marketingApi.createSocial(form)
        : marketingApi.updateSocial(initial.id!, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'social'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      toast.success(isNew ? 'Link added' : 'Link saved');
      onClose();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } }; message?: string })
        .response?.data?.detail ?? (err as Error).message ?? 'Failed to save';
      toast.error(typeof detail === 'string' ? detail : 'Failed to save');
    },
  });

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-md overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold">{isNew ? 'New social link' : 'Edit social link'}</p>
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
          <div>
            <label className="ec-label">Platform</label>
            <select
              className="ec-input"
              value={form.platform}
              onChange={(e) => setForm((f) => ({ ...f, platform: e.target.value }))}
            >
              {SOCIAL_PLATFORM_OPTIONS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="ec-label">Label (optional)</label>
            <input
              className="ec-input"
              value={form.label}
              onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
              placeholder="@handle or display name"
            />
          </div>
          <div>
            <label className="ec-label">URL</label>
            <input
              type="url"
              className="ec-input font-mono"
              required
              value={form.url}
              onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
              placeholder="https://"
            />
          </div>
        </form>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="ec-btn-primary"
            disabled={save.isPending || !form.url.trim()}
            onClick={() => save.mutate()}
          >
            {save.isPending ? 'Saving…' : isNew ? 'Add' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
