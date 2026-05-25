import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  Edit3,
  LayoutTemplate,
  Plus,
  Trash2,
  X,
} from 'lucide-react';
import {
  marketingApi,
  SECTION_TYPE_OPTIONS,
  sectionTypeLabel,
  type MarketingSection,
  type SectionType,
} from '../../lib/marketing';

export function MarketingPagesPage() {
  const qc = useQueryClient();
  const sectionsQ = useQuery({
    queryKey: ['marketing', 'sections'],
    queryFn: () => marketingApi.listSections(),
  });

  const [editing, setEditing] = useState<MarketingSection | null>(null);
  const [creating, setCreating] = useState<SectionType | null>(null);

  const sorted = useMemo(
    () => [...(sectionsQ.data ?? [])].sort((a, b) => a.order - b.order),
    [sectionsQ.data],
  );

  const remove = useMutation({
    mutationFn: (id: string) => marketingApi.deleteSection(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'sections'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      toast.success('Section removed');
    },
  });

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      marketingApi.updateSection(id, { enabled }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'sections'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
    },
  });

  const reorder = useMutation({
    mutationFn: (nextOrder: { id: string; order: number }[]) =>
      marketingApi.reorderSections(nextOrder),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['marketing', 'sections'] }),
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
          <h2 className="text-lg font-semibold">Home page sections</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Drag-free reorder the modular blocks on your home page. Click any
            section to edit its copy and per-type payload.
          </p>
        </div>
        <div className="relative">
          <details className="relative">
            <summary className="ec-btn-primary cursor-pointer list-none">
              <Plus size={16} /> Add section
            </summary>
            <div className="absolute right-0 z-20 mt-2 w-64 overflow-hidden rounded-lg border border-border bg-surface-elevated shadow-lg">
              {SECTION_TYPE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  className="block w-full px-3 py-2 text-left text-sm hover:bg-surface-muted"
                  onClick={() => {
                    setCreating(opt.value);
                    // Close the details element
                    (document.activeElement as HTMLElement)?.blur();
                  }}
                >
                  <span className="font-medium">{opt.label}</span>
                  <span className="block text-xs text-ink-muted">{opt.helper}</span>
                </button>
              ))}
            </div>
          </details>
        </div>
      </div>

      {sectionsQ.isLoading && <p className="text-sm text-ink-muted">Loading sections…</p>}

      {sorted.length === 0 && !sectionsQ.isLoading && (
        <Link
          to="/marketing/templates"
          className="ec-card flex items-center gap-3 border-brand-500/40 bg-brand-600/5 p-4 text-sm transition hover:bg-brand-600/10"
        >
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-600/15 text-brand-600">
            <LayoutTemplate size={16} />
          </span>
          <span className="flex-1">
            <span className="font-semibold">Or start from a template</span>{' '}
            <span className="text-ink-muted">
              — pick a starting point that matches your industry.
            </span>
          </span>
          <ArrowRight size={16} className="shrink-0 text-brand-600" />
        </Link>
      )}

      <div className="ec-card overflow-hidden">
        {sorted.length === 0 && !sectionsQ.isLoading && (
          <p className="p-6 text-center text-sm text-ink-muted">
            No sections yet. Add a hero or services block to get the page started.
          </p>
        )}
        <ul>
          {sorted.map((section, idx) => (
            <li
              key={section.id}
              className="grid grid-cols-[auto_minmax(0,1fr)_auto_auto_auto] items-center gap-3 border-b border-border/60 p-3 last:border-b-0"
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
                  disabled={idx === sorted.length - 1}
                  title="Move down"
                >
                  <ArrowDown size={14} />
                </button>
              </div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="ec-badge bg-brand-600/15 text-brand-600">
                    {sectionTypeLabel(section.type)}
                  </span>
                  <span className="truncate font-medium">
                    {section.title || <span className="italic text-ink-muted">Untitled</span>}
                  </span>
                </div>
                {section.eyebrow && (
                  <p className="mt-0.5 text-xs text-ink-subtle">{section.eyebrow}</p>
                )}
              </div>
              <label className="flex items-center gap-1.5 text-xs text-ink-muted">
                <input
                  type="checkbox"
                  checked={section.enabled}
                  onChange={(e) => toggle.mutate({ id: section.id, enabled: e.target.checked })}
                />
                Visible
              </label>
              <button
                type="button"
                className="ec-btn-secondary !py-1.5 !px-2.5 text-xs"
                onClick={() => setEditing(section)}
              >
                <Edit3 size={13} /> Edit
              </button>
              <button
                type="button"
                className="ec-btn-ghost !px-2 !py-1.5 text-rose-600"
                onClick={() => {
                  if (confirm(`Delete ${sectionTypeLabel(section.type)} section?`)) {
                    remove.mutate(section.id);
                  }
                }}
                title="Delete"
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      </div>

      {editing && (
        <SectionEditorModal section={editing} onClose={() => setEditing(null)} />
      )}
      {creating && (
        <SectionEditorModal
          section={{
            id: '',
            type: creating,
            enabled: true,
            eyebrow: '',
            title: '',
            body: '',
            payload: {},
            order: sorted.length,
          }}
          onClose={() => setCreating(null)}
          isNew
        />
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

type ModalProps = {
  section: MarketingSection;
  isNew?: boolean;
  onClose: () => void;
};

function SectionEditorModal({ section, isNew, onClose }: ModalProps) {
  const qc = useQueryClient();
  const [form, setForm] = useState<MarketingSection>(section);
  const [payloadStr, setPayloadStr] = useState(
    JSON.stringify(section.payload ?? {}, null, 2),
  );
  const [payloadError, setPayloadError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: async () => {
      let payload: Record<string, unknown>;
      try {
        payload = payloadStr.trim() ? JSON.parse(payloadStr) : {};
      } catch (e) {
        setPayloadError((e as Error).message);
        throw new Error('Invalid JSON in payload');
      }
      setPayloadError(null);
      const body = { ...form, payload };
      if (isNew) {
        return marketingApi.createSection(body);
      }
      return marketingApi.updateSection(section.id, body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'sections'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      toast.success(isNew ? 'Section added' : 'Section saved');
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
      <div className="w-full max-w-2xl overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-ink-subtle">
              {isNew ? 'New section' : 'Edit section'}
            </p>
            <p className="font-semibold">{sectionTypeLabel(form.type)}</p>
          </div>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <form
          className="max-h-[70vh] space-y-3 overflow-y-auto p-5"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="ec-label">Eyebrow</label>
              <input
                className="ec-input"
                value={form.eyebrow}
                onChange={(e) => setForm((f) => ({ ...f, eyebrow: e.target.value }))}
              />
            </div>
            <div>
              <label className="ec-label">Title</label>
              <input
                className="ec-input"
                value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              />
            </div>
          </div>
          <div>
            <label className="ec-label">Body</label>
            <textarea
              className="ec-input min-h-[100px]"
              value={form.body}
              onChange={(e) => setForm((f) => ({ ...f, body: e.target.value }))}
            />
          </div>
          <div>
            <label className="ec-label">
              Payload (JSON) — stats, button props, showLimit, etc.
            </label>
            <textarea
              className="ec-input min-h-[160px] font-mono text-xs"
              spellCheck={false}
              value={payloadStr}
              onChange={(e) => {
                setPayloadStr(e.target.value);
                setPayloadError(null);
              }}
            />
            {payloadError && (
              <p className="mt-1 text-xs text-rose-600">Invalid JSON: {payloadError}</p>
            )}
            <p className="mt-1 text-xs text-ink-subtle">
              {form.type === 'hero' && 'Hero supports: { stats: [{label, value}], cta: {label, route} }'}
              {form.type === 'projects' && 'Projects supports: { showLimit: number, featuredOnly: bool }'}
              {form.type === 'cta' && 'CTA supports: { button: {label, route, style} }'}
              {form.type === 'services' && 'Services supports: { showLimit: number }'}
            </p>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
            />
            Visible on the public site
          </label>
        </form>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="ec-btn-primary"
            disabled={save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? 'Saving…' : isNew ? 'Add section' : 'Save section'}
          </button>
        </div>
      </div>
    </div>
  );
}
