import { Database, MoreVertical, Pencil, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { cn } from '../../lib/utils';
import type { KbOut } from '../../lib/knowledge';

type Props = {
  kbs: KbOut[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onEdit: (kb: KbOut) => void;
  onDelete: (kb: KbOut) => void;
  loading?: boolean;
};

export function KbList({ kbs, selectedId, onSelect, onCreate, onEdit, onDelete, loading }: Props) {
  const [menuFor, setMenuFor] = useState<string | null>(null);

  return (
    <aside className="flex flex-col rounded-xl border border-border bg-surface-muted/40">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">
          Knowledge bases
        </p>
        <button
          className="ec-btn-ghost !p-1.5"
          title="New knowledge base"
          onClick={onCreate}
        >
          <Plus size={14} />
        </button>
      </div>

      <div className="flex-1 overflow-auto p-2">
        {loading && (
          <p className="px-2 py-4 text-center text-xs text-ink-muted">Loading…</p>
        )}
        {!loading && kbs.length === 0 && (
          <div className="px-2 py-6 text-center">
            <Database size={20} className="mx-auto mb-2 text-ink-subtle" />
            <p className="text-xs text-ink-muted">No knowledge bases yet.</p>
            <button
              className="mt-3 text-xs text-brand-600 hover:underline"
              onClick={onCreate}
            >
              Create your first KB
            </button>
          </div>
        )}
        {!loading && kbs.length > 0 && (
          <ul className="space-y-1">
            {kbs.map((kb) => (
              <li key={kb.id} className="group relative">
                <button
                  onClick={() => onSelect(kb.id)}
                  className={cn(
                    'flex w-full items-start justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm',
                    selectedId === kb.id
                      ? 'bg-brand-600 text-white'
                      : 'hover:bg-surface-elevated',
                  )}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{kb.name}</span>
                    <span
                      className={cn(
                        'block text-[10px]',
                        selectedId === kb.id ? 'text-white/70' : 'text-ink-subtle',
                      )}
                    >
                      {kb.document_count} doc{kb.document_count === 1 ? '' : 's'} ·{' '}
                      {kb.chunk_count} chunk{kb.chunk_count === 1 ? '' : 's'}
                    </span>
                  </span>
                  <span
                    role="button"
                    tabIndex={0}
                    aria-label="More options"
                    className={cn(
                      'shrink-0 rounded p-0.5 opacity-0 transition group-hover:opacity-100',
                      selectedId === kb.id ? 'hover:bg-white/20' : 'hover:bg-surface-muted',
                    )}
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenuFor(menuFor === kb.id ? null : kb.id);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.stopPropagation();
                        setMenuFor(menuFor === kb.id ? null : kb.id);
                      }
                    }}
                  >
                    <MoreVertical size={12} />
                  </span>
                </button>
                {menuFor === kb.id && (
                  <div
                    className="absolute right-1 top-9 z-20 w-32 overflow-hidden rounded-md border border-border bg-surface-elevated shadow-lg"
                    onMouseLeave={() => setMenuFor(null)}
                  >
                    <button
                      className="flex w-full items-center gap-2 px-3 py-2 text-xs text-ink hover:bg-surface-muted"
                      onClick={() => {
                        setMenuFor(null);
                        onEdit(kb);
                      }}
                    >
                      <Pencil size={12} /> Edit
                    </button>
                    <button
                      className="flex w-full items-center gap-2 px-3 py-2 text-xs text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-900/20"
                      onClick={() => {
                        setMenuFor(null);
                        onDelete(kb);
                      }}
                    >
                      <Trash2 size={12} /> Delete
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
