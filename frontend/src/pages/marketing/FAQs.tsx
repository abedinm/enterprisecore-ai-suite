import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  ArrowDown,
  ArrowUp,
  Edit3,
  HelpCircle,
  Plus,
  Trash2,
  X,
} from 'lucide-react';
import { marketingApi, type FAQInput, type MarketingFAQ } from '../../lib/marketing';

const EMPTY: FAQInput = { question: '', answer: '', order: 0 };

export function MarketingFAQsPage() {
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['marketing', 'faqs'],
    queryFn: () => marketingApi.listFaqs(),
  });

  const sorted = useMemo(
    () => [...(listQ.data ?? [])].sort((a, b) => a.order - b.order),
    [listQ.data],
  );

  const [editing, setEditing] = useState<MarketingFAQ | null>(null);
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => marketingApi.deleteFaq(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'faqs'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      toast.success('FAQ deleted');
    },
  });

  const reorder = useMutation({
    mutationFn: (order: { id: string; order: number }[]) =>
      marketingApi.reorderFaqs(order),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['marketing', 'faqs'] }),
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
          <h2 className="text-lg font-semibold">FAQs</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Frequently asked questions shown on /faq and in the footer.
          </p>
        </div>
        <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
          <Plus size={16} /> New FAQ
        </button>
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading FAQs…</p>}

      {sorted.length === 0 && !listQ.isLoading && (
        <div className="grid place-items-center rounded-xl border border-dashed border-border bg-surface-muted/40 p-10 text-center">
          <HelpCircle size={28} className="mb-3 text-ink-subtle" />
          <p className="font-semibold">No FAQs yet</p>
        </div>
      )}

      <div className="ec-card overflow-hidden">
        <ul>
          {sorted.map((f, idx) => (
            <li key={f.id} className="border-b border-border/60 p-4 last:border-b-0">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold">{f.question}</p>
                  {f.answer && <p className="mt-1 text-sm text-ink-muted">{f.answer}</p>}
                </div>
                <div className="flex shrink-0 gap-1">
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
                    onClick={() => setEditing(f)}
                  >
                    <Edit3 size={12} />
                  </button>
                  <button
                    type="button"
                    className="ec-btn-ghost !px-2 !py-1 text-rose-600"
                    onClick={() => {
                      if (confirm('Delete FAQ?')) remove.mutate(f.id);
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>

      {editing && (
        <FAQModal initial={editing} isNew={false} onClose={() => setEditing(null)} />
      )}
      {creating && (
        <FAQModal
          initial={{ ...EMPTY, order: sorted.length }}
          isNew
          onClose={() => setCreating(false)}
        />
      )}
    </div>
  );
}

function FAQModal({
  initial,
  isNew,
  onClose,
}: {
  initial: FAQInput & { id?: string };
  isNew: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<FAQInput>({
    question: initial.question,
    answer: initial.answer,
    order: initial.order,
  });

  const save = useMutation({
    mutationFn: () =>
      isNew ? marketingApi.createFaq(form) : marketingApi.updateFaq(initial.id!, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'faqs'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      toast.success(isNew ? 'FAQ added' : 'FAQ saved');
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
          <p className="font-semibold">{isNew ? 'New FAQ' : 'Edit FAQ'}</p>
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
            <label className="ec-label">Question</label>
            <input
              className="ec-input"
              required
              value={form.question}
              onChange={(e) => setForm((f) => ({ ...f, question: e.target.value }))}
            />
          </div>
          <div>
            <label className="ec-label">Answer</label>
            <textarea
              className="ec-input min-h-[120px]"
              required
              value={form.answer}
              onChange={(e) => setForm((f) => ({ ...f, answer: e.target.value }))}
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
            disabled={save.isPending || !form.question.trim() || !form.answer.trim()}
            onClick={() => save.mutate()}
          >
            {save.isPending ? 'Saving…' : isNew ? 'Add' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
