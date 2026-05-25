import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Download, ExternalLink, Flame, Library, Plus, Search, Trash2, X } from 'lucide-react';
import {
  academicApi,
  academicDeepApi,
  LMS_KINDS,
  type LmsDeepResource,
  type LmsResource,
  type LmsResourceInput,
} from '../../lib/academic';
import { useAuthStore } from '../../store/auth';
import { isAcademicStaff } from '../../lib/academicRoles';

const EMPTY: LmsResourceInput = {
  class_id: null,
  title: '',
  description: '',
  url: '',
  kind: 'link',
};

export function AcademicLmsPage() {
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const canEdit = isAcademicStaff(user?.role);

  const listQ = useQuery({
    queryKey: ['academic', 'lms'],
    queryFn: () => academicApi.listLmsResources(),
  });
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => academicApi.deleteLmsResource(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'lms'] });
      toast.success('Resource removed');
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">LMS Library</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Shared course materials — slides, videos, PDFs, datasets and links.
          </p>
        </div>
        {canEdit && (
          <button
            type="button"
            className="ec-btn-primary"
            onClick={() => setCreating(true)}
          >
            <Plus size={14} /> Add resource
          </button>
        )}
      </div>

      <LmsSearchAndPopular />

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}

      {listQ.data && listQ.data.length === 0 && (
        <p className="ec-card p-6 text-center text-sm text-ink-muted">
          No resources yet.
        </p>
      )}

      {listQ.data && listQ.data.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {listQ.data.map((r) => (
            <article key={r.id} className="ec-card flex flex-col gap-2 p-4">
              <div className="flex items-start justify-between gap-2">
                <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-600/10 text-brand-600">
                  <Library size={16} />
                </span>
                <span className="ec-badge bg-surface-muted text-ink-muted">
                  {r.kind}
                </span>
              </div>
              <p className="font-semibold">{r.title}</p>
              {r.description && (
                <p className="line-clamp-2 text-xs text-ink-muted">
                  {r.description}
                </p>
              )}
              <div className="mt-auto flex items-center justify-between pt-2">
                {r.url ? (
                  <a
                    href={r.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-brand-600 hover:underline"
                  >
                    Open <ExternalLink size={11} />
                  </a>
                ) : (
                  <span />
                )}
                {canEdit && (
                  <button
                    type="button"
                    className="ec-btn-ghost !px-2 !py-1 text-rose-600"
                    onClick={() => {
                      if (confirm(`Remove "${r.title}"?`)) remove.mutate(r.id);
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      {creating && <LmsModal onClose={() => setCreating(false)} />}
    </div>
  );
}

function LmsSearchAndPopular() {
  const [q, setQ] = useState('');
  const [activeQ, setActiveQ] = useState('');
  const searchQ = useQuery({
    queryKey: ['academic', 'lms', 'search', activeQ],
    queryFn: () =>
      academicDeepApi.searchLmsResources({ q: activeQ || undefined, limit: 20 }),
    enabled: activeQ.length > 0,
  });
  const popularQ = useQuery({
    queryKey: ['academic', 'lms', 'popular'],
    queryFn: () => academicDeepApi.popularLmsResources(5),
  });
  const onDownload = async (id: string, url?: string | null) => {
    try {
      const r = await academicDeepApi.downloadLmsResource(id);
      if (r.url) window.open(r.url, '_blank', 'noopener');
      else if (url) window.open(url, '_blank', 'noopener');
    } catch {
      toast.error('Download failed');
    }
  };
  return (
    <section className="ec-card space-y-3 p-4">
      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setActiveQ(q.trim());
        }}
      >
        <div className="relative flex-1">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted"
          />
          <input
            className="ec-input pl-9"
            placeholder="Search title or description…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <button type="submit" className="ec-btn-secondary">
          Search
        </button>
      </form>
      {activeQ && searchQ.data && (
        <ul className="divide-y divide-border/60 text-sm">
          {searchQ.data.length === 0 && (
            <p className="text-xs text-ink-muted">No results for “{activeQ}”.</p>
          )}
          {searchQ.data.map((r: LmsDeepResource) => (
            <li key={r.id} className="flex items-center justify-between py-2">
              <span className="truncate">{r.title}</span>
              <button
                type="button"
                className="ec-btn-ghost !px-2 !py-1 text-xs"
                onClick={() => onDownload(r.id, r.url)}
              >
                <Download size={12} /> {r.download_count}
              </button>
            </li>
          ))}
        </ul>
      )}
      {popularQ.data && popularQ.data.length > 0 && (
        <div>
          <p className="mb-2 inline-flex items-center gap-1 text-xs font-semibold uppercase text-ink-muted">
            <Flame size={12} className="text-amber-500" /> Popular
          </p>
          <ul className="divide-y divide-border/60 text-sm">
            {popularQ.data.map((r) => (
              <li key={r.id} className="flex items-center justify-between py-2">
                <span className="truncate">{r.title}</span>
                <button
                  type="button"
                  className="ec-btn-ghost !px-2 !py-1 text-xs"
                  onClick={() => onDownload(r.id, r.url)}
                >
                  <Download size={12} /> {r.download_count}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function LmsModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<LmsResourceInput>(EMPTY);
  const save = useMutation({
    mutationFn: () => academicApi.createLmsResource(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'lms'] });
      toast.success('Resource added');
      onClose();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Failed to save');
    },
  });
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold">Add LMS resource</p>
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
            <label className="ec-label">Title</label>
            <input
              required
              className="ec-input"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </div>
          <div>
            <label className="ec-label">Kind</label>
            <select
              className="ec-input"
              value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value })}
            >
              {LMS_KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="ec-label">URL</label>
            <input
              type="url"
              className="ec-input font-mono"
              value={form.url ?? ''}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
              placeholder="https://"
            />
          </div>
          <div>
            <label className="ec-label">Description</label>
            <textarea
              className="ec-input min-h-[80px]"
              value={form.description ?? ''}
              onChange={(e) =>
                setForm({ ...form, description: e.target.value })
              }
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="ec-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className="ec-btn-primary"
              disabled={save.isPending || !form.title.trim()}
            >
              {save.isPending ? 'Saving…' : 'Add'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
