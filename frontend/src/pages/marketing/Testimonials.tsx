import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  ArrowDown,
  ArrowUp,
  Edit3,
  MessageSquareQuote,
  Plus,
  Trash2,
  X,
} from 'lucide-react';
import {
  marketingApi,
  type MarketingTestimonial,
  type TestimonialInput,
} from '../../lib/marketing';

const EMPTY: TestimonialInput = { quote: '', author: '', role: '', order: 0 };

export function MarketingTestimonialsPage() {
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['marketing', 'testimonials'],
    queryFn: () => marketingApi.listTestimonials(),
  });

  const sorted = useMemo(
    () => [...(listQ.data ?? [])].sort((a, b) => a.order - b.order),
    [listQ.data],
  );

  const [editing, setEditing] = useState<MarketingTestimonial | null>(null);
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => marketingApi.deleteTestimonial(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'testimonials'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      toast.success('Testimonial deleted');
    },
  });

  const reorder = useMutation({
    mutationFn: (order: { id: string; order: number }[]) =>
      marketingApi.reorderTestimonials(order),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['marketing', 'testimonials'] }),
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
          <h2 className="text-lg font-semibold">Testimonials</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Quotes from happy clients shown in the testimonials section.
          </p>
        </div>
        <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
          <Plus size={16} /> New testimonial
        </button>
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading testimonials…</p>}

      {sorted.length === 0 && !listQ.isLoading && (
        <div className="grid place-items-center rounded-xl border border-dashed border-border bg-surface-muted/40 p-10 text-center">
          <MessageSquareQuote size={28} className="mb-3 text-ink-subtle" />
          <p className="font-semibold">No testimonials yet</p>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {sorted.map((t, idx) => (
          <article key={t.id} className="ec-card flex h-full flex-col p-4">
            <p className="text-sm italic text-ink">"{t.quote}"</p>
            <div className="mt-3 flex items-end justify-between border-t border-border pt-3">
              <div>
                <p className="font-semibold">{t.author || '—'}</p>
                {t.role && <p className="text-xs text-ink-muted">{t.role}</p>}
              </div>
              <div className="flex gap-1">
                <button
                  type="button"
                  className="ec-btn-ghost !px-1.5 !py-1"
                  onClick={() => move(idx, -1)}
                  disabled={idx === 0}
                >
                  <ArrowUp size={13} />
                </button>
                <button
                  type="button"
                  className="ec-btn-ghost !px-1.5 !py-1"
                  onClick={() => move(idx, +1)}
                  disabled={idx === sorted.length - 1}
                >
                  <ArrowDown size={13} />
                </button>
                <button
                  type="button"
                  className="ec-btn-secondary !px-2 !py-1 text-xs"
                  onClick={() => setEditing(t)}
                >
                  <Edit3 size={12} />
                </button>
                <button
                  type="button"
                  className="ec-btn-ghost !px-2 !py-1 text-rose-600"
                  onClick={() => {
                    if (confirm('Delete testimonial?')) remove.mutate(t.id);
                  }}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>

      {editing && (
        <TestimonialModal
          initial={editing}
          isNew={false}
          onClose={() => setEditing(null)}
        />
      )}
      {creating && (
        <TestimonialModal
          initial={{ ...EMPTY, order: sorted.length }}
          isNew
          onClose={() => setCreating(false)}
        />
      )}
    </div>
  );
}

function TestimonialModal({
  initial,
  isNew,
  onClose,
}: {
  initial: TestimonialInput & { id?: string };
  isNew: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<TestimonialInput>({
    quote: initial.quote,
    author: initial.author,
    role: initial.role,
    order: initial.order,
  });

  const save = useMutation({
    mutationFn: () =>
      isNew
        ? marketingApi.createTestimonial(form)
        : marketingApi.updateTestimonial(initial.id!, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'testimonials'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      toast.success(isNew ? 'Testimonial added' : 'Testimonial saved');
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
      <div className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold">{isNew ? 'New testimonial' : 'Edit testimonial'}</p>
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
            <label className="ec-label">Quote</label>
            <textarea
              className="ec-input min-h-[100px]"
              required
              value={form.quote}
              onChange={(e) => setForm((f) => ({ ...f, quote: e.target.value }))}
            />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="ec-label">Author</label>
              <input
                className="ec-input"
                required
                value={form.author}
                onChange={(e) => setForm((f) => ({ ...f, author: e.target.value }))}
              />
            </div>
            <div>
              <label className="ec-label">Role</label>
              <input
                className="ec-input"
                value={form.role}
                onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
                placeholder="CEO, Acme Inc."
              />
            </div>
          </div>
        </form>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="ec-btn-primary"
            disabled={save.isPending || !form.quote.trim() || !form.author.trim()}
            onClick={() => save.mutate()}
          >
            {save.isPending ? 'Saving…' : isNew ? 'Add' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
