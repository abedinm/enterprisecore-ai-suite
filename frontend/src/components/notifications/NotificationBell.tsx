import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell, CheckCheck } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api, type NotificationCounts, type NotificationItem } from '../../lib/api';
import { cn, relativeTime } from '../../lib/utils';

const LEVEL_BADGE: Record<string, string> = {
  info: 'ec-badge-blue',
  success: 'ec-badge-green',
  warning: 'ec-badge-amber',
  error: 'ec-badge-rose',
};

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  const { data: counts } = useQuery({
    queryKey: ['notification-counts'],
    queryFn: async () => (await api.get<NotificationCounts>('/notifications/counts')).data,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  });

  const { data: items, isFetching } = useQuery({
    queryKey: ['notifications', open],
    queryFn: async () => (await api.get<NotificationItem[]>('/notifications', { params: { limit: 25 } })).data,
    enabled: open,
  });

  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  async function markRead(id: string) {
    await api.post(`/notifications/${id}/read`);
    await queryClient.invalidateQueries({ queryKey: ['notifications'] });
    await queryClient.invalidateQueries({ queryKey: ['notification-counts'] });
  }

  async function markAllRead() {
    await api.post('/notifications/read-all');
    await queryClient.invalidateQueries({ queryKey: ['notifications'] });
    await queryClient.invalidateQueries({ queryKey: ['notification-counts'] });
  }

  const unread = counts?.unread ?? 0;

  return (
    <div ref={containerRef} className="relative">
      <button
        aria-label="Notifications"
        title="Notifications"
        onClick={() => setOpen((v) => !v)}
        className="ec-btn-ghost relative"
      >
        <Bell size={18} />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-[16px] place-items-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold text-white">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-80 max-w-[calc(100vw-1.5rem)] overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-xl sm:w-96">
          <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
            <p className="text-sm font-semibold">Notifications</p>
            <button
              onClick={markAllRead}
              disabled={unread === 0}
              className="flex items-center gap-1 text-xs text-brand-600 hover:underline disabled:opacity-40 disabled:hover:no-underline"
            >
              <CheckCheck size={13} /> Mark all read
            </button>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {isFetching && !items ? (
              <p className="px-4 py-6 text-sm text-ink-muted">Loading…</p>
            ) : items && items.length > 0 ? (
              items.map((n) => (
                <button
                  key={n.id}
                  onClick={() => !n.is_read && markRead(n.id)}
                  className={cn(
                    'block w-full border-b border-border/60 px-4 py-3 text-left transition last:border-b-0',
                    n.is_read ? 'opacity-70' : 'bg-brand-600/5 hover:bg-brand-600/10',
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium">{n.title}</p>
                    <span className={cn('shrink-0', LEVEL_BADGE[n.level] ?? 'ec-badge-blue')}>{n.level}</span>
                  </div>
                  {n.body && <p className="mt-1 text-xs text-ink-muted">{n.body}</p>}
                  <p className="mt-1 text-[11px] text-ink-subtle">{relativeTime(n.created_at)}</p>
                </button>
              ))
            ) : (
              <p className="px-4 py-6 text-sm text-ink-muted">No notifications.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
