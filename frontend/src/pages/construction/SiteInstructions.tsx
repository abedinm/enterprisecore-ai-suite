import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ClipboardList, Plus, Trash2, X } from 'lucide-react';
import {
  constructionApi,
  shortDate,
  type SiteInstruction,
  type SiteInstructionInput,
} from '../../lib/construction';

const EMPTY: SiteInstructionInput = {
  title: '',
  description: '',
  issued_by_id: null,
  issued_to: '',
  issued_at: new Date().toISOString().slice(0, 10),
  response_required_by: null,
  status: 'open',
  response: null,
  responded_at: null,
};

function statusBadge(status: string): string {
  const s = status.toLowerCase();
  if (s.includes('close') || s.includes('resolved')) return 'ec-badge-green';
  if (s.includes('overdue')) return 'ec-badge-rose';
  if (s.includes('pending') || s.includes('open')) return 'ec-badge-amber';
  return 'ec-badge-blue';
}

export function ConstructionSiteInstructionsPage() {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['construction', 'site-instructions', projectId],
    queryFn: () => constructionApi.listSiteInstructions(projectId),
    enabled: !!projectId,
  });

  const [selected, setSelected] = useState<SiteInstruction | null>(null);
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => constructionApi.deleteSiteInstruction(projectId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'site-instructions', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'dashboard', projectId] });
      toast.success('Instruction removed');
    },
  });

  const sorted = (listQ.data ?? []).slice().sort(
    (a, b) => new Date(b.issued_at).getTime() - new Date(a.issued_at).getTime(),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <ClipboardList size={18} className="text-brand-600" /> Site instructions
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Formal directions issued to the contractor (auto-numbered SI-001 onward).
          </p>
        </div>
        <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
          <Plus size={14} /> New instruction
        </button>
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}

      {sorted.length === 0 && !listQ.isLoading && (
        <div className="ec-card flex flex-col items-start gap-3 p-6">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
            <ClipboardList size={22} />
          </div>
          <div>
            <h3 className="font-semibold">No site instructions issued</h3>
            <p className="mt-1 text-sm text-ink-muted">
              Issue your first instruction to start the SI register for this project.
            </p>
          </div>
          <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
            <Plus size={14} /> Issue first instruction
          </button>
        </div>
      )}

      {sorted.length > 0 && (
        <div className="ec-card overflow-hidden">
          <ul>
            {sorted.map((si) => (
              <li
                key={si.id}
                className="grid grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-3 border-b border-border/60 px-4 py-3 last:border-b-0 hover:bg-surface-muted/30"
              >
                <span className="font-mono text-xs text-ink-muted">{si.number}</span>
                <button
                  type="button"
                  className="min-w-0 text-left"
                  onClick={() => setSelected(si)}
                >
                  <p className="truncate font-medium">{si.title}</p>
                  <p className="truncate text-xs text-ink-muted">
                    {shortDate(si.issued_at)}
                    {si.response_required_by && ` · Response by ${shortDate(si.response_required_by)}`}
                    {si.issued_to && ` · → ${si.issued_to}`}
                  </p>
                </button>
                <span className={statusBadge(si.status)}>{si.status}</span>
                <button
                  type="button"
                  className="ec-btn-ghost !px-1.5 !py-1 text-rose-600"
                  onClick={() => {
                    if (confirm(`Delete ${si.number}?`)) remove.mutate(si.id);
                  }}
                >
                  <Trash2 size={14} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {selected && (
        <SiteInstructionDetailModal
          projectId={projectId}
          instruction={selected}
          onClose={() => setSelected(null)}
        />
      )}
      {creating && (
        <SiteInstructionCreateModal
          projectId={projectId}
          onClose={() => setCreating(false)}
        />
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function SiteInstructionDetailModal({
  projectId,
  instruction,
  onClose,
}: {
  projectId: string;
  instruction: SiteInstruction;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [response, setResponse] = useState(instruction.response ?? '');

  const respond = useMutation({
    mutationFn: () =>
      constructionApi.updateSiteInstruction(projectId, instruction.id, {
        response,
        responded_at: new Date().toISOString(),
        status: 'responded',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'site-instructions', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'dashboard', projectId] });
      toast.success('Response saved');
      onClose();
    },
  });

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-2xl overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div>
            <p className="font-mono text-xs text-ink-muted">{instruction.number}</p>
            <p className="font-semibold">{instruction.title}</p>
          </div>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="max-h-[70vh] space-y-4 overflow-y-auto p-5">
          <div className="grid gap-3 text-xs text-ink-muted md:grid-cols-3">
            <div>
              <p className="font-semibold uppercase tracking-wider text-ink-subtle">Issued</p>
              <p className="mt-0.5">{shortDate(instruction.issued_at)}</p>
            </div>
            <div>
              <p className="font-semibold uppercase tracking-wider text-ink-subtle">To</p>
              <p className="mt-0.5">{instruction.issued_to || '—'}</p>
            </div>
            <div>
              <p className="font-semibold uppercase tracking-wider text-ink-subtle">Due by</p>
              <p className="mt-0.5">{shortDate(instruction.response_required_by)}</p>
            </div>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-ink-subtle">Description</p>
            <p className="mt-1 whitespace-pre-line text-sm">{instruction.description}</p>
          </div>
          <div>
            <label className="ec-label">Response</label>
            <textarea
              className="ec-input min-h-[120px]"
              value={response}
              onChange={(e) => setResponse(e.target.value)}
              placeholder="Document your response — date, action taken, refs…"
            />
            {instruction.responded_at && (
              <p className="mt-1 text-xs text-ink-muted">
                Last response: {shortDate(instruction.responded_at)}
              </p>
            )}
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>Close</button>
          <button
            type="button"
            className="ec-btn-primary"
            disabled={respond.isPending || !response.trim()}
            onClick={() => respond.mutate()}
          >
            {respond.isPending ? 'Saving…' : 'Submit response'}
          </button>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function SiteInstructionCreateModal({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<SiteInstructionInput>(EMPTY);

  const save = useMutation({
    mutationFn: () => constructionApi.createSiteInstruction(projectId, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'site-instructions', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'dashboard', projectId] });
      toast.success('Instruction issued');
      onClose();
    },
  });

  const update = <K extends keyof SiteInstructionInput>(key: K, value: SiteInstructionInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-xl overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold">New site instruction</p>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}><X size={16} /></button>
        </div>
        <form
          className="max-h-[70vh] space-y-3 overflow-y-auto p-5"
          onSubmit={(e) => { e.preventDefault(); save.mutate(); }}
        >
          <div>
            <label className="ec-label">Title</label>
            <input required className="ec-input" value={form.title}
              onChange={(e) => update('title', e.target.value)} />
          </div>
          <div>
            <label className="ec-label">Description</label>
            <textarea required className="ec-input min-h-[100px]" value={form.description}
              onChange={(e) => update('description', e.target.value)} />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="ec-label">Issued to</label>
              <input className="ec-input" value={form.issued_to}
                onChange={(e) => update('issued_to', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Issued at</label>
              <input type="date" className="ec-input" value={form.issued_at}
                onChange={(e) => update('issued_at', e.target.value)} />
            </div>
            <div className="md:col-span-2">
              <label className="ec-label">Response required by</label>
              <input type="date" className="ec-input" value={form.response_required_by ?? ''}
                onChange={(e) => update('response_required_by', e.target.value || null)} />
            </div>
          </div>
        </form>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="ec-btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? 'Issuing…' : 'Issue instruction'}
          </button>
        </div>
      </div>
    </div>
  );
}
