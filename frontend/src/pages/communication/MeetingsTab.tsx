import { useQuery } from '@tanstack/react-query';
import { Video, ExternalLink } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';

type Event = { id: string; title: string; description: string | null; starts_at: string; ends_at: string | null; location: string | null };

export function MeetingsTab() {
  const events = useQuery({
    queryKey: ['comm', 'calendar'],
    queryFn: async () => (await api.get<Event[]>('/communication/calendar')).data,
  });

  const now = new Date();
  const upcoming = (events.data ?? []).filter((e) => new Date(e.starts_at) >= now);
  const past = (events.data ?? []).filter((e) => new Date(e.starts_at) < now);

  return (
    <div className="space-y-5">
      <div>
        <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><Video size={14} />Meetings</p>
        <p className="text-sm text-ink-muted">Calendar events drawn from the shared calendar. Add new meetings under <strong>Calendar</strong>.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Section title="Upcoming" events={upcoming} empty="No upcoming meetings." />
        <Section title="Past" events={past.slice(0, 20)} empty="No past meetings." />
      </div>
    </div>
  );
}

function Section({ title, events, empty }: { title: string; events: Event[]; empty: string }) {
  return (
    <div className="ec-card p-5">
      <p className="mb-3 text-sm font-semibold">{title} ({events.length})</p>
      {events.length ? (
        <ul className="space-y-2">
          {events.map((e) => (
            <li key={e.id} className="rounded-lg border border-border bg-surface-muted p-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium">{e.title}</span>
                {e.location && e.location.startsWith('http') && (
                  <a href={e.location} target="_blank" rel="noreferrer" className="text-xs text-brand-600 inline-flex items-center gap-1">
                    join <ExternalLink size={11} />
                  </a>
                )}
              </div>
              <p className="text-xs text-ink-muted">{formatDateTime(e.starts_at)}{e.ends_at && ` → ${formatDateTime(e.ends_at)}`}</p>
              {e.description && <p className="mt-1 text-xs">{e.description}</p>}
            </li>
          ))}
        </ul>
      ) : <p className="text-sm text-ink-muted">{empty}</p>}
    </div>
  );
}
