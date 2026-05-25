/**
 * StatusRegion — wrap a query's loading / error / data branches in
 * accessible status regions so screen-reader users learn when a panel
 * has loaded, failed, or rendered new data.
 *
 *   <StatusRegion
 *     isLoading={q.isLoading}
 *     isError={q.isError}
 *     error={q.error}
 *     loadingLabel="Loading invoices"
 *   >
 *     <InvoicesTable rows={q.data!} />
 *   </StatusRegion>
 *
 * Pairs with `<LiveAnnouncer />` for one-shot announcements like
 * "Saved" or "Deleted".
 */
import type { ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import { useAnnouncerStore } from '../hooks/useAnnouncer';

export type StatusRegionProps = {
  isLoading?: boolean;
  isError?: boolean;
  error?: unknown;
  loadingLabel?: string;
  errorLabel?: string;
  /** Render this when neither loading nor error. Required. */
  children: ReactNode;
};

function extractMessage(err: unknown, fallback: string): string {
  if (!err) return fallback;
  if (typeof err === 'string') return err;
  const e = err as { response?: { data?: { detail?: string } }; message?: string };
  return e.response?.data?.detail ?? e.message ?? fallback;
}

export function StatusRegion({
  isLoading,
  isError,
  error,
  loadingLabel = 'Loading…',
  errorLabel = 'Could not load data.',
  children,
}: StatusRegionProps) {
  if (isLoading) {
    return (
      <div role="status" aria-live="polite" className="flex items-center gap-2 text-sm text-ink-muted">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        <span className="sr-only">{loadingLabel}</span>
        <span aria-hidden="true">{loadingLabel}</span>
      </div>
    );
  }
  if (isError) {
    return (
      <div
        role="alert"
        className="ec-card border-rose-300 bg-rose-50 p-3 text-sm text-rose-700 dark:bg-rose-900/20 dark:text-rose-300"
      >
        {extractMessage(error, errorLabel)}
      </div>
    );
  }
  return <>{children}</>;
}

/**
 * LiveAnnouncer — invisible polite + assertive aria-live region. Mounts
 * once at the AppShell so any call site can `announce(...)` without
 * rendering its own region.
 */
export function LiveAnnouncer() {
  const polite = useAnnouncerStore((s) => s.polite);
  const assertive = useAnnouncerStore((s) => s.assertive);
  return (
    <>
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {polite}
      </div>
      <div role="alert" aria-live="assertive" aria-atomic="true" className="sr-only">
        {assertive}
      </div>
    </>
  );
}
