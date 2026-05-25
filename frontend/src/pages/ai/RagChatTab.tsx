import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { BookOpen, Database, Send } from 'lucide-react';
import toast from 'react-hot-toast';
import { CitationText } from '../../components/knowledge/CitationText';
import { SourcesPanel, type SourceItem } from '../../components/knowledge/SourcesPanel';
import { api } from '../../lib/api';
import { knowledgeApi, streamSse, type KbOut } from '../../lib/knowledge';

type Turn = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  sources?: SourceItem[];
  inflight?: boolean;
};

type Provider = { anthropic: boolean; openai: boolean; ollama: boolean };

export function RagChatTab() {
  const kbsQuery = useQuery({
    queryKey: ['knowledge', 'kbs'],
    queryFn: knowledgeApi.listKbs,
  });
  const providers = useQuery({
    queryKey: ['ai', 'providers'],
    queryFn: async () => (await api.get<Provider>('/ai/providers')).data,
  });

  const [selectedKbs, setSelectedKbs] = useState<string[]>([]);
  const [provider, setProvider] = useState<'anthropic' | 'openai' | 'ollama'>('ollama');
  const [topK, setTopK] = useState(6);
  const [temperature, setTemperature] = useState(0.3);
  const [draft, setDraft] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [highlight, setHighlight] = useState<number | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [inflight, setInflight] = useState(false);

  // Auto-select first KB once loaded
  useEffect(() => {
    if (!kbsQuery.data || selectedKbs.length > 0) return;
    const ready = kbsQuery.data.filter((k) => k.ready_count > 0);
    if (ready.length > 0) setSelectedKbs([ready[0].id]);
    else if (kbsQuery.data.length > 0) setSelectedKbs([kbsQuery.data[0].id]);
  }, [kbsQuery.data]);

  // Pick best available provider
  useEffect(() => {
    if (!providers.data) return;
    if (providers.data.anthropic) setProvider('anthropic');
    else if (providers.data.openai) setProvider('openai');
    else setProvider('ollama');
  }, [providers.data]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [turns]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && inflight) cancel();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [inflight]);

  const selectedKbObjects = useMemo(() => {
    if (!kbsQuery.data) return [];
    return kbsQuery.data.filter((k) => selectedKbs.includes(k.id));
  }, [kbsQuery.data, selectedKbs]);

  const embeddingModelsAgree = useMemo(() => {
    if (selectedKbObjects.length <= 1) return true;
    const m = `${selectedKbObjects[0].embedding_provider}/${selectedKbObjects[0].embedding_model}`;
    return selectedKbObjects.every((k) => `${k.embedding_provider}/${k.embedding_model}` === m);
  }, [selectedKbObjects]);

  function toggleKb(id: string) {
    setSelectedKbs((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  }

  function cancel() {
    abortRef.current?.abort();
    abortRef.current = null;
    setInflight(false);
  }

  async function send() {
    const text = draft.trim();
    if (!text || inflight) return;
    if (selectedKbs.length === 0) {
      toast.error('Select at least one knowledge base');
      return;
    }
    if (!embeddingModelsAgree) {
      toast.error('Selected KBs use different embedding models — pick KBs with matching models');
      return;
    }
    const userTurn: Turn = { id: crypto.randomUUID(), role: 'user', text };
    const asstTurn: Turn = {
      id: crypto.randomUUID(),
      role: 'assistant',
      text: '',
      sources: [],
      inflight: true,
    };
    setTurns((t) => [...t, userTurn, asstTurn]);
    setDraft('');
    setHighlight(null);
    setInflight(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamSse(
        '/knowledge/rag/chat',
        {
          kb_ids: selectedKbs,
          messages: [{ role: 'user', content: text }],
          provider,
          top_k: topK,
          temperature,
          max_tokens: 1500,
          conversation_id: conversationId,
        },
        {
          onSources: (data) => {
            const chunks: SourceItem[] = (data.chunks ?? []).map((c: any) => ({
              index: c.index,
              chunk_id: c.chunk_id,
              document_id: c.document_id,
              document_name: c.document_name,
              kb_id: c.kb_id,
              kb_name: c.kb_name,
              page_number: c.page_number,
              score: c.score,
              text: c.text,
            }));
            setTurns((t) =>
              t.map((x) => (x.id === asstTurn.id ? { ...x, sources: chunks } : x)),
            );
          },
          onToken: (token) => {
            setTurns((t) =>
              t.map((x) => (x.id === asstTurn.id ? { ...x, text: x.text + token } : x)),
            );
          },
          onUsage: (meta) => {
            if (meta.conversation_id) setConversationId(meta.conversation_id);
          },
          onError: (detail) => toast.error(detail || 'RAG failed'),
          onDone: () => {
            setTurns((t) =>
              t.map((x) => (x.id === asstTurn.id ? { ...x, inflight: false } : x)),
            );
          },
          signal: controller.signal,
        },
      );
    } catch (e: any) {
      if (e?.name !== 'AbortError') toast.error(e?.message || 'Stream failed');
    } finally {
      setInflight(false);
      abortRef.current = null;
      setTurns((t) =>
        t.map((x) => (x.id === asstTurn.id ? { ...x, inflight: false } : x)),
      );
    }
  }

  function resetConversation() {
    cancel();
    setTurns([]);
    setConversationId(null);
    setHighlight(null);
  }

  // Sources for the most recent assistant turn drive the right panel
  const latestSources = useMemo(() => {
    for (let i = turns.length - 1; i >= 0; i--) {
      if (turns[i].role === 'assistant' && (turns[i].sources?.length ?? 0) > 0) {
        return turns[i].sources!;
      }
    }
    return [];
  }, [turns]);

  return (
    <div className="grid h-[calc(100vh-22rem)] min-h-[480px] gap-3 lg:grid-cols-[1fr_320px]">
      <main className="flex flex-col overflow-hidden rounded-xl border border-border bg-surface-elevated">
        <header className="space-y-2 border-b border-border bg-surface-muted px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <BookOpen size={14} className="text-ink-muted" />
            <span className="text-sm font-medium">RAG Chat</span>
            <span className="ml-auto text-xs text-ink-subtle">
              {turns.length === 0
                ? 'Ask a question across your knowledge bases'
                : `${turns.filter((t) => t.role === 'user').length} question${
                    turns.filter((t) => t.role === 'user').length === 1 ? '' : 's'
                  } in this conversation`}
            </span>
            <button
              className="ec-btn-ghost !py-1 text-xs"
              onClick={resetConversation}
              disabled={turns.length === 0 && !conversationId}
            >
              New conversation
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex flex-wrap items-center gap-1">
              {kbsQuery.data?.length ? (
                kbsQuery.data.map((k) => (
                  <KbChip
                    key={k.id}
                    kb={k}
                    active={selectedKbs.includes(k.id)}
                    onClick={() => toggleKb(k.id)}
                  />
                ))
              ) : (
                <span className="text-xs text-ink-muted">No knowledge bases yet. Create one in the Knowledge tab.</span>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 border-t border-border pt-3 text-xs text-ink-muted">
            <label className="flex items-center gap-1.5">
              <span>Provider</span>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value as any)}
                className="ec-input !w-28 !py-1 text-xs"
              >
                <option value="anthropic" disabled={!providers.data?.anthropic}>Anthropic</option>
                <option value="openai" disabled={!providers.data?.openai}>OpenAI</option>
                <option value="ollama">Ollama</option>
              </select>
            </label>
            <label className="flex items-center gap-1.5">
              <span>Top-K</span>
              <input
                type="range"
                min={1}
                max={15}
                step={1}
                value={topK}
                onChange={(e) => setTopK(parseInt(e.target.value, 10))}
                className="w-20"
              />
              <span className="tabular-nums">{topK}</span>
            </label>
            <label className="flex items-center gap-1.5">
              <span>Temp</span>
              <input
                type="range"
                min={0}
                max={1.5}
                step={0.05}
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="w-20"
              />
              <span className="tabular-nums">{temperature.toFixed(2)}</span>
            </label>
            {!embeddingModelsAgree && (
              <span className="rounded bg-rose-100 px-2 py-0.5 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300">
                Selected KBs use different embedding models
              </span>
            )}
          </div>
        </header>

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-auto p-4">
          {turns.length === 0 ? (
            <div className="grid h-full place-items-center text-center">
              <div className="max-w-sm">
                <Database size={28} className="mx-auto mb-2 text-ink-subtle" />
                <p className="text-sm font-medium">
                  {kbsQuery.data?.length
                    ? 'Pick a KB above and ask a question'
                    : 'Create a knowledge base first'}
                </p>
                <p className="mt-1 text-xs text-ink-muted">
                  Answers stream live and cite the document chunks they used.
                </p>
              </div>
            </div>
          ) : (
            turns.map((t) =>
              t.role === 'user' ? (
                <div key={t.id} className="ml-12 rounded-lg bg-brand-50 p-3 text-sm dark:bg-brand-900/20">
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">you</p>
                  <pre className="whitespace-pre-wrap font-sans">{t.text}</pre>
                </div>
              ) : (
                <div key={t.id} className="mr-12 rounded-lg bg-surface-muted p-3 text-sm">
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
                    assistant
                    {t.inflight && <span className="ml-2 text-brand-600">streaming…</span>}
                    {!t.inflight && (t.sources?.length ?? 0) > 0 && (
                      <span className="ml-2 text-ink-subtle">{t.sources!.length} sources</span>
                    )}
                  </p>
                  {t.text ? (
                    <CitationText text={t.text} highlightIndex={highlight} onCite={(i) => setHighlight(i === highlight ? null : i)} />
                  ) : (
                    <p className="italic text-ink-muted">retrieving sources…</p>
                  )}
                  {t.inflight && (
                    <span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-brand-600 align-middle" />
                  )}
                </div>
              ),
            )
          )}
        </div>

        <div className="border-t border-border p-3">
          <div className="flex items-end gap-2">
            <textarea
              className="ec-input flex-1 min-h-[60px]"
              placeholder="Ask anything about the selected knowledge bases…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && draft.trim()) {
                  send();
                }
              }}
            />
            {inflight ? (
              <button className="ec-btn-danger" onClick={cancel}>
                Stop
              </button>
            ) : (
              <button
                className="ec-btn-primary"
                disabled={!draft.trim() || selectedKbs.length === 0}
                onClick={send}
              >
                <Send size={14} /> Ask
              </button>
            )}
          </div>
          <p className="mt-1 text-xs text-ink-subtle">
            Ctrl/⌘+Enter to send · Esc to stop · sources appear in the right panel.
          </p>
        </div>
      </main>

      <SourcesPanel sources={latestSources} highlightIndex={highlight} onHighlight={setHighlight} />
    </div>
  );
}

function KbChip({ kb, active, onClick }: { kb: KbOut; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`group flex items-center gap-1 rounded-full px-2.5 py-1 text-xs transition ${
        active
          ? 'bg-brand-600 text-white'
          : 'bg-surface-elevated text-ink-muted hover:text-ink'
      }`}
      title={`${kb.ready_count}/${kb.document_count} docs ready · ${kb.embedding_model}`}
    >
      <Database size={11} />
      <span className="truncate max-w-[160px]">{kb.name}</span>
      <span className={`text-[10px] ${active ? 'text-white/70' : 'text-ink-subtle'}`}>
        {kb.ready_count}
      </span>
    </button>
  );
}
