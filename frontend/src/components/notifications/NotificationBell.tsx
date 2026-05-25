import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell, CheckCheck } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
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
  // Detect new-unread transitions so we can shake the bell.
  const prevUnreadRef = useRef(unread);
  const [shaking, setShaking] = useState(false);
  useEffect(() => {
    if (unread > prevUnreadRef.current) {
      setShaking(true);
      const t = window.setTimeout(() => setShaking(false), 700);
      prevUnreadRef.current = unread;
      return () => window.clearTimeout(t);
    }
    prevUnreadRef.current = unread;
  }, [unread]);

  return (
    <div ref={containerRef} className="relative">
      <motion.button
        aria-label={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'}
        title="Notifications"
        onClick={() => setOpen((v) => !v)}
        className="ec-btn-ghost relative"
        whileHover={{ rotate: [-6, 6, -4, 4, 0] }}
        transition={{ duration: 0.45 }}
      >
        <motion.span
          animate={shaking ? { rotate: [-12, 12, -8, 8, 0] } : { rotate: 0 }}
          transition={{ duration: 0.6 }}
          className="inline-flex"
        >
          <Bell size={18} />
        </motion.span>
        <AnimatePresence>
          {unread > 0 && (
            <motion.span
              key={unread}
              initial={{ scale: 0.4, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.4, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 380, damping: 18 }}
              className="absolute -right-0.5 -top-0.5 grid h-4 min-w-[16px] place-items-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold text-white"
            >
              <span aria-hidden="true" className="absolute inset-0 rounded-full bg-rose-500 opacity-60 animate-pulse-glow" />
              <span className="relative z-10">{unread > 99 ? '99+' : unread}</span>
            </motion.span>
          )}
        </AnimatePresence>
      </motion.button>
      <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0, y: -6, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -4, scale: 0.98 }}
          transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          className="absolute right-0 z-40 mt-2 w-80 max-w-[calc(100vw-1.5rem)] overflow-hidden rounded-xl border border-border bg-surface-elevated/80 shadow-floating backdrop-blur-xl sm:w-96">
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
        </motion.div>
      )}
      </AnimatePresence>
    </div>
  );
}
