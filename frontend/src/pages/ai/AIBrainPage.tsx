import { useState } from 'react';
import {
  BarChart3, BookOpen, Bot, Brain, Cpu, Database, FileText, Heart,
  MessageSquare, PenLine, Search,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { ChatTab } from './ChatTab';
import { WriterTab } from './WriterTab';
import { SentimentTab } from './SentimentTab';
import { SmartSearchTab } from './SmartSearchTab';
import { UsageTab } from './UsageTab';
import { MeetingTab } from './MeetingTab';
import { ChatbotsTab } from './ChatbotsTab';
import { KnowledgeTab } from './KnowledgeTab';
import { RagChatTab } from './RagChatTab';
import { ModelManagerTab } from './ModelManagerTab';

type TabKey =
  | 'chat'
  | 'rag'
  | 'knowledge'
  | 'writer'
  | 'sentiment'
  | 'search'
  | 'meeting'
  | 'chatbots'
  | 'models'
  | 'usage';

const TABS: { key: TabKey; label: string; icon: typeof MessageSquare }[] = [
  { key: 'chat', label: 'Chat', icon: MessageSquare },
  { key: 'rag', label: 'RAG Chat', icon: BookOpen },
  { key: 'knowledge', label: 'Knowledge', icon: Database },
  { key: 'writer', label: 'Writer', icon: PenLine },
  { key: 'sentiment', label: 'Sentiment', icon: Heart },
  { key: 'search', label: 'Smart Search', icon: Search },
  { key: 'meeting', label: 'Meeting Summary', icon: FileText },
  { key: 'chatbots', label: 'Chatbots', icon: Bot },
  { key: 'models', label: 'Models', icon: Cpu },
  { key: 'usage', label: 'Usage & Cost', icon: BarChart3 },
];

export function AIBrainPage() {
  const [active, setActive] = useState<TabKey>('chat');
  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-brand-600">Module workspace</p>
        <h1 className="mt-1 flex items-center gap-2 text-3xl font-semibold">
          <Brain size={26} className="text-brand-600" />
          AI Brain
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-muted">
          Cross-module AI tools — chat with Claude/OpenAI/Ollama, write emails or
          memos, classify sentiment, summarise meetings, search across all your data
          in natural language, build embeddable chatbots, and watch usage &amp; spend.
        </p>
      </div>

      <div className="ec-card overflow-hidden">
        <div className="flex flex-wrap gap-1 border-b border-border bg-surface-muted px-2 py-2">
          {TABS.map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.key}
                onClick={() => setActive(t.key)}
                className={cn(
                  'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition',
                  active === t.key
                    ? 'bg-brand-600 text-white shadow-sm'
                    : 'text-ink-muted hover:bg-surface-elevated hover:text-ink',
                )}
              >
                <Icon size={15} /> {t.label}
              </button>
            );
          })}
        </div>
        <div className="p-5">
          {active === 'chat' && <ChatTab />}
          {active === 'rag' && <RagChatTab />}
          {active === 'knowledge' && <KnowledgeTab />}
          {active === 'writer' && <WriterTab />}
          {active === 'sentiment' && <SentimentTab />}
          {active === 'search' && <SmartSearchTab />}
          {active === 'meeting' && <MeetingTab />}
          {active === 'chatbots' && <ChatbotsTab />}
          {active === 'models' && <ModelManagerTab />}
          {active === 'usage' && <UsageTab />}
        </div>
      </div>
    </div>
  );
}
