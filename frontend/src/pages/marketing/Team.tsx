import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  ArrowDown,
  ArrowUp,
  Edit3,
  Image as ImageIcon,
  Plus,
  Trash2,
  User,
  Users,
  X,
} from 'lucide-react';
import {
  marketingApi,
  type MarketingTeamMember,
  type TeamInput,
} from '../../lib/marketing';
import { MediaPickerDialog } from './Media';

const EMPTY: TeamInput = { name: '', role: '', imageId: null, order: 0 };

export function MarketingTeamPage() {
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['marketing', 'team'],
    queryFn: () => marketingApi.listTeam(),
  });
  const uploadsQ = useQuery({
    queryKey: ['marketing', 'uploads'],
    queryFn: () => marketingApi.listUploads(),
  });

  const sorted = useMemo(
    () => [...(listQ.data ?? [])].sort((a, b) => a.order - b.order),
    [listQ.data],
  );

  const [editing, setEditing] = useState<MarketingTeamMember | null>(null);
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => marketingApi.deleteTeam(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'team'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      toast.success('Team member removed');
    },
  });

  const reorder = useMutation({
    mutationFn: (order: { id: string; order: number }[]) =>
      marketingApi.reorderTeam(order),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['marketing', 'team'] }),
  });

  function move(idx: number, delta: number) {
    const target = idx + delta;
    if (target < 0 || target >= sorted.length) return;
    const next = [...sorted];
    [next[idx], next[target]] = [next[target], next[idx]];
    reorder.mutate(next.map((s, i) => ({ id: s.id, order: i })));
  }

  const findImg = (id: string | null) =>
    id ? uploadsQ.data?.find((u) => u.id === id) : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Team</h2>
          <p className="mt-1 text-sm text-ink-muted">
            People shown in the about / team section.
          </p>
        </div>
        <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
          <Plus size={16} /> Add member
        </button>
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading team…</p>}

      {sorted.length === 0 && !listQ.isLoading && (
        <div className="grid place-items-center rounded-xl border border-dashed border-border bg-surface-muted/40 p-10 text-center">
          <Users size={28} className="mb-3 text-ink-subtle" />
          <p className="font-semibold">No team members yet</p>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {sorted.map((m, idx) => {
          const img = findImg(m.imageId);
          return (
            <article key={m.id} className="ec-card flex h-full flex-col items-center p-4 text-center">
              <div className="h-20 w-20 overflow-hidden rounded-full border border-border bg-surface-muted">
                {img ? (
                  <img src={img.url} alt={m.name} className="h-full w-full object-cover" />
                ) : (
                  <div className="grid h-full w-full place-items-center text-ink-subtle">
                    <User size={28} />
                  </div>
                )}
              </div>
              <p className="mt-2 font-semibold">{m.name}</p>
              {m.role && <p className="text-xs text-ink-muted">{m.role}</p>}
              <div className="mt-3 flex gap-1">
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
                  onClick={() => setEditing(m)}
                >
                  <Edit3 size={12} />
                </button>
                <button
                  type="button"
                  className="ec-btn-ghost !px-2 !py-1 text-rose-600"
                  onClick={() => {
                    if (confirm(`Remove ${m.name}?`)) remove.mutate(m.id);
                  }}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </article>
          );
        })}
      </div>

      {editing && (
        <TeamModal initial={editing} isNew={false} onClose={() => setEditing(null)} />
      )}
      {creating && (
        <TeamModal
          initial={{ ...EMPTY, order: sorted.length }}
          isNew
          onClose={() => setCreating(false)}
        />
      )}
    </div>
  );
}

function TeamModal({
  initial,
  isNew,
  onClose,
}: {
  initial: TeamInput & { id?: string };
  isNew: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<TeamInput>({
    name: initial.name,
    role: initial.role,
    imageId: initial.imageId,
    order: initial.order,
  });
  const [pickerOpen, setPickerOpen] = useState(false);

  const uploadsQ = useQuery({
    queryKey: ['marketing', 'uploads'],
    queryFn: () => marketingApi.listUploads(),
  });

  const img = form.imageId ? uploadsQ.data?.find((u) => u.id === form.imageId) : null;

  const save = useMutation({
    mutationFn: () =>
      isNew ? marketingApi.createTeam(form) : marketingApi.updateTeam(initial.id!, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'team'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      toast.success(isNew ? 'Member added' : 'Member saved');
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
          <p className="font-semibold">{isNew ? 'Add team member' : 'Edit team member'}</p>
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
              <label className="ec-label">Name</label>
              <input
                className="ec-input"
                required
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div>
              <label className="ec-label">Role</label>
              <input
                className="ec-input"
                value={form.role}
                onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
                placeholder="Founder"
              />
            </div>
          </div>
          <div>
            <label className="ec-label">Headshot</label>
            <div className="flex items-center gap-3">
              <div className="h-16 w-16 overflow-hidden rounded-full border border-border bg-surface-muted">
                {img ? (
                  <img src={img.url} alt={form.name} className="h-full w-full object-cover" />
                ) : (
                  <div className="grid h-full w-full place-items-center text-ink-subtle">
                    <ImageIcon size={20} />
                  </div>
                )}
              </div>
              <button
                type="button"
                className="ec-btn-secondary"
                onClick={() => setPickerOpen(true)}
              >
                {img ? 'Change' : 'Pick image'}
              </button>
              {img && (
                <button
                  type="button"
                  className="ec-btn-ghost text-rose-600"
                  onClick={() => setForm((f) => ({ ...f, imageId: null }))}
                >
                  <X size={14} /> Clear
                </button>
              )}
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
            disabled={save.isPending || !form.name.trim()}
            onClick={() => save.mutate()}
          >
            {save.isPending ? 'Saving…' : isNew ? 'Add' : 'Save'}
          </button>
        </div>
      </div>
      <MediaPickerDialog
        open={pickerOpen}
        selectedId={form.imageId}
        onClose={() => setPickerOpen(false)}
        onPick={(u) => setForm((f) => ({ ...f, imageId: u.id }))}
      />
    </div>
  );
}
