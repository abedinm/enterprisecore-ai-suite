import { useEffect, useRef, useState } from 'react';
import { WifiOff } from 'lucide-react';

const HIDE_DELAY_MS = 2_000;

export function OfflineBanner() {
  const [offline, setOffline] = useState(() =>
    typeof navigator !== 'undefined' ? !navigator.onLine : false,
  );
  const [visible, setVisible] = useState(offline);
  const hideTimerRef = useRef<number | null>(null);

  useEffect(() => {
    const clearHide = () => {
      if (hideTimerRef.current !== null) {
        window.clearTimeout(hideTimerRef.current);
        hideTimerRef.current = null;
      }
    };
    const handleOffline = () => {
      clearHide();
      setOffline(true);
      setVisible(true);
    };
    const handleOnline = () => {
      setOffline(false);
      // Delay hiding to avoid flicker on flaky connections.
      clearHide();
      hideTimerRef.current = window.setTimeout(() => {
        setVisible(false);
        hideTimerRef.current = null;
      }, HIDE_DELAY_MS);
    };

    window.addEventListener('offline', handleOffline);
    window.addEventListener('online', handleOnline);
    return () => {
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('online', handleOnline);
      clearHide();
    };
  }, []);

  if (!visible) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="sticky top-0 z-40 flex items-center justify-center gap-2 bg-amber-500/95 px-3 py-1.5 text-xs font-medium text-amber-950 backdrop-blur"
    >
      <WifiOff size={14} aria-hidden="true" />
      <span>
        {offline
          ? "You're offline — recent data may be stale and new changes can't sync yet."
          : 'Back online — syncing.'}
      </span>
    </div>
  );
}
