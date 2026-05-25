import { useCallback, useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Bot, MessageSquare, User } from 'lucide-react';
import { languageLabel, webchatApi } from '../../lib/webchat';
import { formatDateTime, relativeTime } from '../../lib/utils';
import { cn } from '../../lib/utils';
import { useWebSocket } from '../../hooks/useWebSocket';
import type { RealtimeMessage } from '../../lib/realtime';

export function ConversationsViewer() {
  const { botId } = useParams<{ botId: string }>();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const bot = useQuery({
    queryKey: ['webchat', 'bot', botId],
    queryFn: () => webchatApi.getBot(botId!),
    enabled: Boolean(botId),
  });

  const conversations = useQuery({
    queryKey: ['webchat', 'conversations', botId],
    queryFn: () => webchatApi.listConversations(botId!, 50),
    enabled: Boolean(botId),
  });

  // Realtime — when a new message lands on this bot the server pushes a
  // ``webchat.update`` frame. We invalidate the relevant TanStack
  // queries so the visible list + active conversation refetch without
  // the user needing to refresh.
  const onRealtime = useCallback(
    (msg: RealtimeMessage) => {
      if (msg.type !== 'webchat.update') return;
      queryClient.invalidateQueries({ queryKey: ['webchat', 'conversations', botId] });
      const convoId = msg.conversation_id as string | undefined;
      if (convoId) {
        queryClient.invalidateQueries({ queryKey: ['webchat', 'conversation', convoId] });
      }
    },
    [queryClient, botId],
  );
  useWebSocket(botId ? `/ws/webchat/${botId}` : '', {
    enabled: Boolean(botId),
    onMessage: onRealtime,
  });

  // Auto-select the first conversation when the list loads.
  useEffect(() => {
    if (!selectedId && conversations.data && conversations.data.length > 0) {
      setSelectedId(conversations.data[0].id);
    }
  }, [conversations.data, selectedId]);

  const conversation = useQuery({
    queryKey: ['webchat', 'conversation', selectedId],
    queryFn: () => webchatApi.getConversation(selectedId!),
    enabled: Boolean(selectedId),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link to="/webchat" className="ec-btn-ghost mb-2 !px-2 !py-1 text-xs">
            <ArrowLeft size={14} /> Back to bots
          </Link>
          <h1 className="flex items-center gap-2 text-2xl font-semibold sm:text-3xl">
            <MessageSquare className="text-brand-600" size={24} />
            Conversations
            {bot.data && <span className="text-ink-muted font-normal">· {bot.data.name}</span>}
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-muted">
            Read every exchange this bot has had with visitors. Conversations
            are grouped by visitor session.
          </p>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <div className="ec-card overflow-hidden">
          <div className="border-b border-border bg-surface-muted px-3 py-2 text-xs uppercase tracking-wider text-ink-muted">
            {conversations.data?.length ?? 0} conversations
          </div>
          <div className="max-h-[70vh] overflow-y-auto">
            {conversations.isLoading && (
              <p className="p-4 text-sm text-ink-muted">Loading…</p>
            )}
            {conversations.data && conversations.data.length === 0 && (
              <p className="p-4 text-sm text-ink-muted">
                No conversations yet. Once a visitor sends a message through the
                embed widget, it'll appear here.
              </p>
            )}
            {conversations.data?.map((c) => {
              const active = c.id === selectedId;
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setSelectedId(c.id)}
                  className={cn(
                    'w-full border-b border-border/60 px-3 py-2.5 text-left text-sm transition',
                    active ? 'bg-brand-600/10' : 'hover:bg-surface-muted',
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-medium">
                      {c.contact_hint || c.visitor_session_id.slice(0, 12)}
                    </span>
                    <span className="text-[11px] text-ink-subtle whitespace-nowrap">
                      {relativeTime(c.last_message_at ?? c.created_at)}
                    </span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-[11px] text-ink-muted">
                    <span>{c.message_count} msgs</span>
                    {c.language_detected && (
                      <span className="ec-badge bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300">
                        {languageLabel(c.language_detected)}
                      </span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="ec-card overflow-hidden">
          {!selectedId && (
            <p className="p-8 text-center text-sm text-ink-muted">
              Select a conversation on the left to read it.
            </p>
          )}
          {selectedId && conversation.isLoading && (
            <p className="p-4 text-sm text-ink-muted">Loading conversation…</p>
          )}
          {selectedId && conversation.data && (
            <div className="flex flex-col">
              <div className="border-b border-border bg-surface-muted px-4 py-3">
                <p className="text-sm font-semibold">
                  {conversation.data.contact_hint || `Visitor ${conversation.data.visitor_session_id.slice(0, 12)}`}
                </p>
                <p className="mt-0.5 text-xs text-ink-muted">
                  Started {formatDateTime(conversation.data.created_at)} ·
                  {' '}{conversation.data.messages.length} messages
                  {conversation.data.language_detected && (
                    <> · primary {languageLabel(conversation.data.language_detected)}</>
                  )}
                </p>
              </div>
              <div className="max-h-[70vh] space-y-3 overflow-y-auto p-4">
                {conversation.data.messages.length === 0 && (
                  <p className="text-sm text-ink-muted">No messages in this conversation.</p>
                )}
                {conversation.data.messages.map((m) => (
                  <MessageRow key={m.id} role={m.role} content={m.content}
                    languageDetected={m.language_detected} createdAt={m.created_at} />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MessageRow({
  role, content, languageDetected, createdAt,
}: {
  role: string;
  content: string;
  languageDetected: string | null;
  createdAt: string;
}) {
  const isUser = role === 'user';
  return (
    <div className={cn('flex gap-3', isUser ? 'flex-row' : 'flex-row-reverse')}>
      <div
        className={cn(
          'grid h-8 w-8 shrink-0 place-items-center rounded-full',
          isUser ? 'bg-surface-muted text-ink-muted' : 'bg-brand-600 text-white',
        )}
      >
        {isUser ? <User size={15} /> : <Bot size={15} />}
      </div>
      <div className={cn('flex-1 min-w-0', isUser ? 'text-left' : 'text-right')}>
        <div
          className={cn(
            'inline-block max-w-full whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm',
            isUser
              ? 'rounded-tl-sm bg-surface-muted text-ink'
              : 'rounded-tr-sm bg-brand-600 text-white',
          )}
        >
          {content}
        </div>
        <div className={cn('mt-1 flex items-center gap-2 text-[11px] text-ink-subtle', isUser ? 'justify-start' : 'justify-end')}>
          <span>{formatDateTime(createdAt)}</span>
          {languageDetected && (
            <span className="ec-badge bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300">
              {languageLabel(languageDetected)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
