// Header pill that reflects the WebSocket connection state — green
// when connected, amber while reconnecting, gray when disconnected.
// Reads the same shared client as the useRealtimeNotifications hook so
// they reflect the same socket.

import { useEffect, useState } from 'react';
import { acquireRealtime, releaseRealtime, type RealtimeStatus } from '../lib/realtime';
import { cn } from '../lib/utils';

interface RealtimeStatusProps {
  // Override the channel — defaults to the user's notifications channel
  // which AppShell always has open.
  path?: string;
  className?: string;
}

const LABEL: Record<RealtimeStatus, string> = {
  connected: 'Live',
  connecting: 'Reconnecting',
  disconnected: 'Offline',
};

const DOT_CLASS: Record<RealtimeStatus, string> = {
  connected: 'bg-emerald-500',
  connecting: 'bg-amber-500 animate-pulse',
  disconnected: 'bg-zinc-400',
};

export function RealtimeStatus({ path = '/ws/notifications', className }: RealtimeStatusProps) {
  const [status, setStatus] = useState<RealtimeStatus>('disconnected');

  useEffect(() => {
    const client = acquireRealtime(path);
    const off = client.onStatus(setStatus);
    return () => {
      off();
      releaseRealtime(path);
    };
  }, [path]);

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-muted px-2 py-0.5 text-[11px] font-medium text-ink-muted',
        className,
      )}
      title={`Realtime: ${LABEL[status]}`}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', DOT_CLASS[status])} />
      {LABEL[status]}
    </span>
  );
}
