import { useEffect, useState } from 'react';
import { RefreshCw, X } from 'lucide-react';
import { applyPWAUpdate } from '../lib/pwa';

const AUTO_DISMISS_MS = 60_000;
const UPDATE_EVENT = 'pwa:update-available';

export function UpdateAvailableBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onUpdate = () => setVisible(true);
    window.addEventListener(UPDATE_EVENT, onUpdate as EventListener);
    return () => window.removeEventListener(UPDATE_EVENT, onUpdate as EventListener);
  }, []);

  useEffect(() => {
    if (!visible) return undefined;
    const timer = window.setTimeout(() => setVisible(false), AUTO_DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [visible]);

  if (!visible) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-4 right-4 z-50 flex max-w-sm items-center gap-3 rounded-xl border border-border bg-surface-elevated px-4 py-3 shadow-lg"
    >
      <RefreshCw size={18} className="shrink-0 text-brand-600 dark:text-brand-300" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium leading-tight">New version available</p>
        <p className="text-xs text-ink-muted">Restart now to pick up the latest changes.</p>
      </div>
      <button
        type="button"
        onClick={applyPWAUpdate}
        className="ec-btn-primary px-3 py-1.5 text-xs"
      >
        Restart
      </button>
      <button
        type="button"
        aria-label="Dismiss update notice"
        onClick={() => setVisible(false)}
        className="ec-btn-ghost px-1.5 py-1.5"
      >
        <X size={14} />
      </button>
    </div>
  );
}
