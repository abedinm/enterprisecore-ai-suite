import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { MessageSquare, Plus, Send, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { cn } from '../../lib/utils';
import { api } from '../../lib/api';

type Provider = { anthropic: boolean; openai: boolean; ollama: boolean };
type Conversation = {
  id: string; title: string; provider: string; model: string | null;
  created_at: string; updated_at: string;
};
type Message = {
  id: string; conversation_id: string; role: string; content: string;
  tokens_in: number; tokens_out: number; created_at: string;
};
type ChatResponse = {
  text: string; provider: string; model: string;
  tokens_in: number; tokens_out: number; cost_usd: string;
  latency_ms: number; conversation_id: string;
};

export function ChatTab() {
  const qc = useQueryClient();
  const providers = useQuery({
    queryKey: ['ai', 'providers'],
    queryFn: async () => (await api.get<Provider>('/ai/providers')).data,
  });
  const convs = useQuery({
    queryKey: ['ai', 'conversations'],
    queryFn: async () => (await api.get<Conversation[]>('/ai/conversations')).data,
  });

  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [provider, setProvider] = useState<'anthropic' | 'openai' | 'ollama'>('ollama');
  const scrollRef = useRef<HTMLDivElement>(null);

  const messages = useQuery({
    enabled: !!selected,
    queryKey: ['ai', 'conversation', selected],
    queryFn: async () => (await api.get<Message[]>(`/ai/conversations/${selected}/messages`)).data,
  });

  useEffect(() => {
    // Prefer the first available paid provider if configured
    if (!providers.data) return;
    if (providers.data.anthropic) setProvider('anthropic');
    else if (providers.data.openai) setProvider('openai');
    else setProvider('ollama');
  }, [providers.data]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.data]);

  const send = useMutation({
    mutationFn: async () => {
      const body = {
        conversation_id: selected,
        provider,
        messages: [{ role: 'user', content: draft }],
        max_tokens: 1200,
        temperature: 0.7,
        feature: 'chat',
      };
      return (await api.post<ChatResponse>('/ai/chat', body)).data;
    },
    onSuccess: (r) => {
      setSelected(r.conversation_id);
      setDraft('');
      qc.invalidateQueries({ queryKey: ['ai', 'conversations'] });
      qc.invalidateQueries({ queryKey: ['ai', 'conversation', r.conversation_id] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Chat failed'),
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/ai/conversations/${id}`)).data,
    onSuccess: () => {
      setSelected(null);
      qc.invalidateQueries({ queryKey: ['ai', 'conversations'] });
    },
  });

  return (
    <div className="grid h-[calc(100vh-22rem)] min-h-[480px] gap-3 lg:grid-cols-[260px_1fr]">
      <aside className="flex flex-col rounded-xl border border-border bg-surface-muted/40">
        <div className="flex items-center justify-between border-b border-border px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">Conversations</p>
          <button className="ec-btn-ghost" onClick={() => setSelected(null)} title="New conversation"><Plus size={14} /></button>
        </div>
        <div className="flex-1 overflow-auto p-2">
          {convs.data?.length ? (
            <ul className="space-y-1">
              {convs.data.map((c) => (
                <li key={c.id}>
                  <button
                    onClick={() => setSelected(c.id)}
                    className={cn('flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm',
                      selected === c.id ? 'bg-brand-600 text-white' : 'hover:bg-surface-elevated')}
                  >
                    <span className="truncate">{c.title}</span>
                    <span className={cn('shrink-0 text-[10px] uppercase',
                      selected === c.id ? 'text-white/70' : 'text-ink-subtle')}>{c.provider}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-2 py-6 text-center text-xs text-ink-muted">No conversations yet.</p>
          )}
        </div>
      </aside>

      <main className="flex flex-col rounded-xl border border-border bg-surface-elevated overflow-hidden">
        <div className="flex items-center justify-between border-b border-border bg-surface-muted px-3 py-2">
          <div className="flex items-center gap-2">
            <MessageSquare size={14} className="text-ink-muted" />
            <span className="text-sm font-medium">
              {selected ? convs.data?.find((c) => c.id === selected)?.title : 'New conversation'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <select className="ec-input !py-1 !w-32 text-xs" value={provider}
                    onChange={(e) => setProvider(e.target.value as any)}>
              <option value="anthropic" disabled={!providers.data?.anthropic}>Anthropic</option>
              <option value="openai" disabled={!providers.data?.openai}>OpenAI</option>
              <option value="ollama">Ollama (local)</option>
            </select>
            {selected && (
              <button className="ec-btn-ghost text-rose-600" title="Delete conversation"
                      onClick={() => { if (confirm('Delete conversation?')) remove.mutate(selected); }}>
                <Trash2 size={14} />
              </button>
            )}
          </div>
        </div>

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-auto p-4">
          {messages.data?.length ? messages.data.map((m) => (
            <div key={m.id} className={cn('rounded-lg p-3 text-sm',
              m.role === 'user' ? 'ml-12 bg-brand-50 dark:bg-brand-900/20' : 'mr-12 bg-surface-muted')}>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
                {m.role}
                {m.tokens_in > 0 && <span className="ml-2 font-normal text-ink-subtle">{m.tokens_in}↑ {m.tokens_out}↓</span>}
              </p>
              <pre className="whitespace-pre-wrap font-sans">{m.content}</pre>
            </div>
          )) : (
            <p className="grid h-full place-items-center text-sm text-ink-muted">
              {selected ? 'Loading…' : 'Type below to start a new conversation.'}
            </p>
          )}
        </div>

        <div className="border-t border-border p-3">
          <div className="flex items-end gap-2">
            <textarea
              className="ec-input flex-1 min-h-[60px]"
              placeholder="Type a message…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && draft.trim()) {
                  send.mutate();
                }
              }}
            />
            <button className="ec-btn-primary" disabled={!draft.trim() || send.isPending}
                    onClick={() => send.mutate()}>
              <Send size={14} /> {send.isPending ? '…' : 'Send'}
            </button>
          </div>
          <p className="mt-1 text-xs text-ink-subtle">Ctrl/⌘+Enter to send · Anthropic/OpenAI require an API key in Settings.</p>
        </div>
      </main>
    </div>
  );
}
