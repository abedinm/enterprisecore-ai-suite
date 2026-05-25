import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Plus, Trash2, Users2 } from 'lucide-react';
import { Modal, ModalHeader, ModalBody, ModalFooter, ModalClose } from '../../components/Modal';
import { constructionApi, type RaciEntry, type RaciEntryInput } from '../../lib/construction';

const EMPTY: RaciEntryInput = {
  activity: '',
  responsible_user_id: null,
  accountable_user_id: null,
  consulted: [],
  informed: [],
  notes: '',
};

type Role = 'R' | 'A' | 'C' | 'I' | '';

function roleClass(role: Role): string {
  switch (role) {
    case 'R': return 'bg-emerald-500/80 text-white';
    case 'A': return 'bg-rose-500/80 text-white';
    case 'C': return 'bg-blue-500/80 text-white';
    case 'I': return 'bg-amber-500/80 text-white';
    default: return 'bg-surface-muted text-ink-subtle';
  }
}

function roleFor(entry: RaciEntry, user: string): Role {
  if (entry.responsible_user_id === user) return 'R';
  if (entry.accountable_user_id === user) return 'A';
  if (entry.consulted.includes(user)) return 'C';
  if (entry.informed.includes(user)) return 'I';
  return '';
}

export function ConstructionRaciPage() {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['construction', 'raci', projectId],
    queryFn: () => constructionApi.listRaci(projectId),
    enabled: !!projectId,
  });

  const [editing, setEditing] = useState<RaciEntry | null>(null);
  const [creating, setCreating] = useState(false);

  // Auto-derive the user column list from all referenced users in the matrix.
  const users = useMemo(() => {
    const set = new Set<string>();
    for (const e of listQ.data ?? []) {
      if (e.responsible_user_id) set.add(e.responsible_user_id);
      if (e.accountable_user_id) set.add(e.accountable_user_id);
      for (const u of e.consulted) set.add(u);
      for (const u of e.informed) set.add(u);
    }
    return Array.from(set).sort();
  }, [listQ.data]);

  const remove = useMutation({
    mutationFn: (id: string) => constructionApi.deleteRaciEntry(projectId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'raci', projectId] });
      toast.success('Activity removed');
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Users2 size={18} className="text-brand-600" /> RACI matrix
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Responsibility assignment per activity. R = Responsible, A = Accountable,
            C = Consulted, I = Informed. Click any cell to edit.
          </p>
        </div>
        <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
          <Plus size={14} /> New activity
        </button>
      </div>

      <div className="flex flex-wrap gap-2 text-xs">
        <span className="ec-badge bg-emerald-500/80 text-white">R Responsible</span>
        <span className="ec-badge bg-rose-500/80 text-white">A Accountable</span>
        <span className="ec-badge bg-blue-500/80 text-white">C Consulted</span>
        <span className="ec-badge bg-amber-500/80 text-white">I Informed</span>
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}

      {listQ.data && listQ.data.length === 0 && (
        <div className="ec-card flex flex-col items-start gap-3 p-6">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
            <Users2 size={22} />
          </div>
          <div>
            <h3 className="font-semibold">No RACI entries yet</h3>
            <p className="mt-1 text-sm text-ink-muted">
              Add an activity to start mapping responsibilities for your team.
            </p>
          </div>
          <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
            <Plus size={14} /> Add first activity
          </button>
        </div>
      )}

      {listQ.data && listQ.data.length > 0 && (
        <div className="ec-card overflow-x-auto">
          <table className="min-w-full border-collapse text-sm">
            <thead>
              <tr className="bg-surface-muted/40 text-left text-xs uppercase tracking-wider text-ink-subtle">
                <th className="px-3 py-2">Activity</th>
                {users.map((u) => (
                  <th key={u} className="border-l border-border px-2 py-2 text-center" title={u}>
                    <span className="font-mono">{u.slice(0, 8)}</span>
                  </th>
                ))}
                <th className="border-l border-border px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {listQ.data.map((entry) => (
                <tr
                  key={entry.id}
                  className="border-t border-border/60 hover:bg-surface-muted/30"
                >
                  <td
                    className="cursor-pointer px-3 py-2 font-medium"
                    onClick={() => setEditing(entry)}
                  >
                    {entry.activity}
                  </td>
                  {users.map((u) => {
                    const role = roleFor(entry, u);
                    return (
                      <td key={u} className="border-l border-border px-1 py-1 text-center">
                        <button
                          type="button"
                          onClick={() => setEditing(entry)}
                          className={`mx-auto grid h-7 w-7 place-items-center rounded-md text-xs font-semibold ${roleClass(role)}`}
                        >
                          {role || '·'}
                        </button>
                      </td>
                    );
                  })}
                  <td className="border-l border-border px-2 py-1 text-right">
                    <button
                      type="button"
                      className="ec-btn-ghost !px-1.5 !py-1 text-rose-600"
                      onClick={() => {
                        if (confirm(`Delete activity "${entry.activity}"?`)) remove.mutate(entry.id);
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(editing || creating) && (
        <RaciModal
          projectId={projectId}
          entry={editing}
          isNew={creating}
          onClose={() => { setCreating(false); setEditing(null); }}
        />
      )}
    </div>
  );
}

function RaciModal({
  projectId,
  entry,
  isNew,
  onClose,
}: {
  projectId: string;
  entry: RaciEntry | null;
  isNew: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<RaciEntryInput>(
    entry
      ? {
          activity: entry.activity,
          responsible_user_id: entry.responsible_user_id ?? null,
          accountable_user_id: entry.accountable_user_id ?? null,
          consulted: entry.consulted,
          informed: entry.informed,
          notes: entry.notes ?? '',
        }
      : EMPTY,
  );

  const [consultedStr, setConsultedStr] = useState(form.consulted.join(', '));
  const [informedStr, setInformedStr] = useState(form.informed.join(', '));

  const save = useMutation({
    mutationFn: () => {
      const body: RaciEntryInput = {
        ...form,
        consulted: consultedStr.split(',').map((s) => s.trim()).filter(Boolean),
        informed: informedStr.split(',').map((s) => s.trim()).filter(Boolean),
      };
      if (isNew) return constructionApi.createRaciEntry(projectId, body);
      if (!entry) throw new Error('No entry');
      return constructionApi.updateRaciEntry(projectId, entry.id, body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'raci', projectId] });
      toast.success(isNew ? 'Activity added' : 'Activity saved');
      onClose();
    },
  });

  const update = <K extends keyof RaciEntryInput>(key: K, value: RaciEntryInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  return (
    <Modal open onClose={onClose} size="lg" labelledBy="raci-modal-title">
      <ModalHeader>
        <p id="raci-modal-title" className="font-semibold">{isNew ? 'New activity' : 'Edit activity'}</p>
        <ModalClose onClose={onClose} />
      </ModalHeader>
      <form onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <div className="max-h-[70vh] space-y-3 overflow-y-auto p-5">
          <div>
            <label className="ec-label">Activity</label>
            <input required className="ec-input" value={form.activity}
              onChange={(e) => update('activity', e.target.value)} />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="ec-label">Responsible (R) — user id</label>
              <input className="ec-input" value={form.responsible_user_id ?? ''}
                onChange={(e) => update('responsible_user_id', e.target.value || null)} />
            </div>
            <div>
              <label className="ec-label">Accountable (A) — user id</label>
              <input className="ec-input" value={form.accountable_user_id ?? ''}
                onChange={(e) => update('accountable_user_id', e.target.value || null)} />
            </div>
          </div>
          <div>
            <label className="ec-label">Consulted (C) — comma-separated user ids</label>
            <input className="ec-input" value={consultedStr}
              onChange={(e) => setConsultedStr(e.target.value)} />
          </div>
          <div>
            <label className="ec-label">Informed (I) — comma-separated user ids</label>
            <input className="ec-input" value={informedStr}
              onChange={(e) => setInformedStr(e.target.value)} />
          </div>
          <div>
            <label className="ec-label">Notes</label>
            <textarea className="ec-input min-h-[60px]" value={form.notes ?? ''}
              onChange={(e) => update('notes', e.target.value)} />
          </div>
        </div>
        <ModalFooter>
          <button type="button" className="ec-btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="ec-btn-primary" disabled={save.isPending}>
            {save.isPending ? 'Saving…' : isNew ? 'Add' : 'Save'}
          </button>
        </ModalFooter>
      </form>
    </Modal>
  );
}
