import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { MessageSquare, Paperclip, Plus, Trash2, Users, X } from 'lucide-react';
import {
  constructionApi,
  shortDate,
  type ToolboxTalkInput,
} from '../../lib/construction';

const EMPTY: ToolboxTalkInput = {
  topic: '',
  conducted_by_id: null,
  conducted_at: new Date().toISOString().slice(0, 10),
  attendees_count: 0,
  key_points: '',
  attachments: [],
  notes: '',
};

export function ConstructionToolboxPage() {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['construction', 'toolbox-talks', projectId],
    queryFn: () => constructionApi.listToolboxTalks(projectId),
    enabled: !!projectId,
  });
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => constructionApi.deleteToolboxTalk(projectId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'toolbox-talks', projectId] });
      toast.success('Talk removed');
    },
  });

  const sorted = (listQ.data ?? []).slice().sort(
    (a, b) => new Date(b.conducted_at).getTime() - new Date(a.conducted_at).getTime(),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <MessageSquare size={18} className="text-brand-600" /> Toolbox talks
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Safety briefings and pre-task talks conducted on site.
          </p>
        </div>
        <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
          <Plus size={14} /> Log a talk
        </button>
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}

      {sorted.length === 0 && !listQ.isLoading && (
        <div className="ec-card flex flex-col items-start gap-3 p-6">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
            <MessageSquare size={22} />
          </div>
          <div>
            <h3 className="font-semibold">No toolbox talks logged</h3>
            <p className="mt-1 text-sm text-ink-muted">
              Capture daily or weekly safety briefings here for compliance records.
            </p>
          </div>
          <button type="button" className="ec-btn-primary" onClick={() => setCreating(true)}>
            <Plus size={14} /> Log first talk
          </button>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {sorted.map((t) => (
          <article key={t.id} className="ec-card flex flex-col gap-2 p-4">
            <div className="flex items-start justify-between gap-2">
              <p className="font-semibold leading-snug">{t.topic}</p>
              <button
                type="button"
                className="ec-btn-ghost !px-1.5 !py-1 text-rose-600"
                onClick={() => { if (confirm('Delete this talk?')) remove.mutate(t.id); }}
              >
                <Trash2 size={14} />
              </button>
            </div>
            <p className="text-xs text-ink-muted">{shortDate(t.conducted_at)}</p>
            {t.key_points && (
              <p className="line-clamp-3 text-sm text-ink-muted">{t.key_points}</p>
            )}
            <div className="mt-auto flex flex-wrap items-center gap-2 pt-2 text-xs text-ink-muted">
              <span className="ec-badge bg-surface-muted text-ink-muted inline-flex items-center gap-1">
                <Users size={11} /> {t.attendees_count}
              </span>
              {t.attachments.length > 0 && (
                <span className="ec-badge bg-surface-muted text-ink-muted inline-flex items-center gap-1">
                  <Paperclip size={11} /> {t.attachments.length}
                </span>
              )}
            </div>
          </article>
        ))}
      </div>

      {creating && (
        <ToolboxModal
          projectId={projectId}
          onClose={() => setCreating(false)}
        />
      )}
    </div>
  );
}

function ToolboxModal({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<ToolboxTalkInput>(EMPTY);
  const [attachStr, setAttachStr] = useState('');

  const update = <K extends keyof ToolboxTalkInput>(key: K, value: ToolboxTalkInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const save = useMutation({
    mutationFn: () => {
      const attachments = attachStr
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);
      return constructionApi.createToolboxTalk(projectId, { ...form, attachments });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'toolbox-talks', projectId] });
      toast.success('Talk logged');
      onClose();
    },
  });

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-xl overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold">Log toolbox talk</p>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}><X size={16} /></button>
        </div>
        <form
          className="max-h-[70vh] space-y-3 overflow-y-auto p-5"
          onSubmit={(e) => { e.preventDefault(); save.mutate(); }}
        >
          <div>
            <label className="ec-label">Topic</label>
            <input required className="ec-input" value={form.topic}
              onChange={(e) => update('topic', e.target.value)} />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="ec-label">Date</label>
              <input type="date" className="ec-input" value={form.conducted_at}
                onChange={(e) => update('conducted_at', e.target.value)} />
            </div>
            <div>
              <label className="ec-label">Attendees</label>
              <input type="number" min={0} className="ec-input" value={form.attendees_count}
                onChange={(e) => update('attendees_count', Math.max(0, Number(e.target.value) || 0))} />
            </div>
          </div>
          <div>
            <label className="ec-label">Key points</label>
            <textarea className="ec-input min-h-[100px]" value={form.key_points}
              onChange={(e) => update('key_points', e.target.value)} />
          </div>
          <div>
            <label className="ec-label">Attachments (one URL per line)</label>
            <textarea className="ec-input min-h-[60px] font-mono text-xs" value={attachStr}
              onChange={(e) => setAttachStr(e.target.value)} />
          </div>
          <div>
            <label className="ec-label">Notes</label>
            <textarea className="ec-input min-h-[60px]" value={form.notes ?? ''}
              onChange={(e) => update('notes', e.target.value)} />
          </div>
        </form>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="ec-btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? 'Saving…' : 'Log talk'}
          </button>
        </div>
      </div>
    </div>
  );
}
