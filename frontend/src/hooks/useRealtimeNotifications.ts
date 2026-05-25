// Connects to /ws/notifications once per session and surfaces server
// events as react-hot-toast toasts. The hook returns nothing — it's
// imported for its side effect from <AppShell>.

import { useEffect } from 'react';
import { toast } from 'react-hot-toast';
import { tokenStore } from '../lib/api';
import { useWebSocket } from './useWebSocket';
import type { RealtimeMessage } from '../lib/realtime';

type ToastLevel = 'success' | 'error' | 'warning' | 'info';

function emitToast(level: ToastLevel, title: string, body: string): void {
  // react-hot-toast doesn't have a native "warning" style — we use the
  // default icon-less toast for warning/info to stay visually distinct
  // from success/error.
  const text = body ? `${title}: ${body}` : title;
  if (level === 'success') {
    toast.success(text);
  } else if (level === 'error') {
    toast.error(text);
  } else {
    toast(text);
  }
}

export function useRealtimeNotifications() {
  // Only open the socket once the user is authenticated. Without a
  // token the server closes with 1008 and we'd churn reconnects.
  const enabled = Boolean(tokenStore.getAccess());

  const { status } = useWebSocket('/ws/notifications', {
    enabled,
    onMessage(msg: RealtimeMessage) {
      if (msg.type !== 'notification') return;
      const title = (msg.title as string) || 'Notification';
      const body = (msg.body as string) || '';
      const level = ((msg.level as ToastLevel) || 'info');
      emitToast(level, title, body);
    },
  });

  // Re-check token on auth changes — opening the app while logged-out
  // and then logging in should kick the hook into "enabled".
  useEffect(() => {
    if (typeof window === 'undefined') return;
    function onStorage(ev: StorageEvent) {
      if (ev.key === 'ec_access_token') {
        // Trigger a remount of dependent components via a synthetic event.
        window.dispatchEvent(new Event('ec:auth-changed'));
      }
    }
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  return { status };
}
