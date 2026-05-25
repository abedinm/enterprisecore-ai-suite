import { FileText } from 'lucide-react';

export type SourceItem = {
  index: number;
  chunk_id: string;
  document_id: string;
  document_name: string;
  kb_id: string;
  kb_name: string;
  page_number: number | null;
  score: number;
  text: string;
};

type Props = {
  sources: SourceItem[];
  highlightIndex: number | null;
  onHighlight: (index: number | null) => void;
};

export function SourcesPanel({ sources, highlightIndex, onHighlight }: Props) {
  return (
    <aside className="flex flex-col rounded-xl border border-border bg-surface-muted/40">
      <div className="border-b border-border px-3 py-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">
          Sources
        </p>
        <p className="mt-0.5 text-[11px] text-ink-subtle">
          {sources.length ? `${sources.length} retrieved chunk${sources.length === 1 ? '' : 's'}` : 'Waiting for retrieval…'}
        </p>
      </div>
      <div className="flex-1 overflow-auto p-2">
        {sources.length === 0 && (
          <div className="grid h-full place-items-center px-2 text-center">
            <div>
              <FileText size={20} className="mx-auto mb-1 text-ink-subtle" />
              <p className="text-xs text-ink-muted">
                Sources used to answer the question will appear here.
              </p>
            </div>
          </div>
        )}
        <ul className="space-y-2">
          {sources.map((s) => (
            <li key={s.chunk_id}>
              <button
                onMouseEnter={() => onHighlight(s.index)}
                onMouseLeave={() => onHighlight(null)}
                onClick={() => onHighlight(s.index === highlightIndex ? null : s.index)}
                className={`block w-full rounded-lg border p-2 text-left text-xs transition ${
                  highlightIndex === s.index
                    ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20'
                    : 'border-border bg-surface-elevated hover:border-brand-300'
                }`}
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="inline-flex items-center gap-1 font-mono text-[10px] font-bold text-brand-700 dark:text-brand-300">
                    [{s.index}]
                  </span>
                  <span className="text-[10px] text-ink-subtle">
                    score {s.score.toFixed(3)}
                  </span>
                </div>
                <p className="mt-1 text-[11px] font-medium text-ink">
                  {s.document_name}
                  {s.page_number !== null && (
                    <span className="ml-1 text-ink-subtle">· p.{s.page_number}</span>
                  )}
                </p>
                <p className="mt-0.5 text-[10px] uppercase tracking-wider text-ink-subtle">
                  {s.kb_name}
                </p>
                <p className="mt-1 line-clamp-4 text-[11px] text-ink-muted">{s.text}</p>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
