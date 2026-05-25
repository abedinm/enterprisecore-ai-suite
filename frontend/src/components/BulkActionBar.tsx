/**
 * BulkActionBar — sticky bar that appears once any rows are selected.
 *
 * Sticks to the bottom of the list container with a subtle shadow. Use
 * inside any list view to expose batch actions (delete, archive, export,
 * tag…). The bar fades out when count drops to 0.
 *
 *   <BulkActionBar
 *     count={sel.size}
 *     onClear={sel.clear}
 *     entityLabel="invoice"
 *   >
 *     <button onClick={...} className="btn-secondary">Export CSV</button>
 *     <button onClick={...} className="btn-danger">Delete</button>
 *   </BulkActionBar>
 */
import { ReactNode } from 'react';
import { X } from 'lucide-react';

type Props = {
  count: number;
  onClear: () => void;
  entityLabel?: string;
  children?: ReactNode;
};

export function BulkActionBar({ count, onClear, entityLabel = 'item', children }: Props) {
  if (count === 0) return null;
  const plural = count === 1 ? entityLabel : `${entityLabel}s`;
  return (
    <div
      role="region"
      aria-label={`${count} ${plural} selected`}
      className="sticky bottom-4 z-30 mx-auto mt-4 flex max-w-3xl items-center justify-between gap-3 rounded-lg border border-border bg-surface px-4 py-2 shadow-lg"
    >
      <div className="flex items-center gap-3 text-sm">
        <button
          type="button"
          onClick={onClear}
          aria-label="Clear selection"
          className="grid h-6 w-6 place-items-center rounded-full text-ink-muted hover:bg-surface-muted"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
        <span className="font-medium">{count} {plural} selected</span>
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}
