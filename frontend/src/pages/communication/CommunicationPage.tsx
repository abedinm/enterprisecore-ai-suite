import { useState } from 'react';
import { MessageSquare, Megaphone, Calendar, Video, StickyNote, BarChart3, MessageCircle, BookOpen } from 'lucide-react';
import { cn } from '../../lib/utils';
import { MessagesTab } from './MessagesTab';
import { AnnouncementsTab } from './AnnouncementsTab';
import { CalendarTab } from './CalendarTab';
import { MeetingsTab } from './MeetingsTab';
import { NotesTab } from './NotesTab';
import { PollsTab } from './PollsTab';
import { FeedbackTab } from './FeedbackTab';
import { WikiTab } from './WikiTab';

type TabKey = 'messages' | 'announcements' | 'calendar' | 'meetings' | 'notes' | 'polls' | 'feedback' | 'wiki';

const tabs: { key: TabKey; label: string; icon: typeof MessageSquare }[] = [
  { key: 'messages', label: 'Messages', icon: MessageSquare },
  { key: 'announcements', label: 'Announcements', icon: Megaphone },
  { key: 'calendar', label: 'Calendar', icon: Calendar },
  { key: 'meetings', label: 'Meetings', icon: Video },
  { key: 'notes', label: 'Notes', icon: StickyNote },
  { key: 'polls', label: 'Polls', icon: BarChart3 },
  { key: 'feedback', label: 'Feedback', icon: MessageCircle },
  { key: 'wiki', label: 'Wiki', icon: BookOpen },
];

export function CommunicationPage() {
  const [active, setActive] = useState<TabKey>('messages');
  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-brand-600">Module workspace</p>
        <h1 className="mt-1 flex items-center gap-2 text-3xl font-semibold">
          <MessageSquare className="text-brand-600" size={26} />
          Communication
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-muted">
          8 offline collaboration tools — threaded messaging, company announcements, calendar, meetings,
          shared notes, polls with live tallies, anonymous feedback, and team wiki.
        </p>
      </div>
      <div className="ec-card overflow-hidden">
        <div className="flex flex-wrap gap-1 border-b border-border bg-surface-muted px-2 py-2">
          {tabs.map((t) => {
            const Icon = t.icon;
            return (
              <button key={t.key} onClick={() => setActive(t.key)}
                className={cn('flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition',
                  active === t.key ? 'bg-brand-600 text-white shadow-sm' : 'text-ink-muted hover:bg-surface-elevated hover:text-ink')}>
                <Icon size={15} /> {t.label}
              </button>
            );
          })}
        </div>
        <div className="p-5">
          {active === 'messages' && <MessagesTab />}
          {active === 'announcements' && <AnnouncementsTab />}
          {active === 'calendar' && <CalendarTab />}
          {active === 'meetings' && <MeetingsTab />}
          {active === 'notes' && <NotesTab />}
          {active === 'polls' && <PollsTab />}
          {active === 'feedback' && <FeedbackTab />}
          {active === 'wiki' && <WikiTab />}
        </div>
      </div>
    </div>
  );
}
