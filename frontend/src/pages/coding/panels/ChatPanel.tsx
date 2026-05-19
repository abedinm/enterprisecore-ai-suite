import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Bot, Loader2, Paperclip, Send, Sparkles, User2, X } from 'lucide-react';
import toast from 'react-hot-toast';
import { cn } from '../../../lib/utils';
import { codingChat } from '../api';
import { DEFAULT_MODEL, PROVIDER_LABELS, PROVIDER_MODELS } from '../providers';
import type { AiProvider, ChatMessage, EditorTab } from '../types';

type Props = {
  projectId: string | null;
  tabs: EditorTab[];
  activePath: string | null;
  provider: AiProvider;
  model: string;
  apiKey: string | null;
  onModelChange: (m: string) => void;
  onProviderChange: (p: AiProvider) => void;
  onInsert: (code: string) => void;
};

const SUGGESTIONS = [
  'Explain the current file step by step',
  'Generate a unit test for the active selection',
  'Refactor this code to use async/await',
  'Add comprehensive docstrings to this file',
  'Find potential bugs and security issues',
];

export function ChatPanel({
  projectId, tabs, activePath, provider, model, apiKey,
  onModelChange, onProviderChange, onInsert,
}: Props) {
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [prompt, setPrompt] = useState('');
  const [contextFiles, setContextFiles] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (activePath && contextFiles.length === 0) {
      setContextFiles([activePath]);
    }
  }, [activePath]);  // eslint-disable-line react-hooks/exhaustive-deps

  const send = useMutation({
    mutationFn: async () => {
      const next = [...history, { role: 'user' as const, content: prompt }];
      const res = await codingChat({
        messages: next,
        provider,
        model,
        api_key_override: apiKey,
        project_id: projectId ?? undefined,
        context_files: contextFiles,
        max_tokens: 2400,
        temperature: 0.4,
      });
      return { next, res };
    },
    onSuccess: ({ next, res }) => {
      setHistory([...next, { role: 'assistant', content: res.text }]);
      setPrompt('');
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || e?.message || 'Chat failed'),
  });

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [history, send.isPending]);

  const blocks = useMemo(() => history.map((m) => splitCodeBlocks(m.content)), [history]);

  const canSubmit = !!prompt.trim() && !send.isPending;

  return (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 items-center gap-2 border-b border-border bg-surface-muted px-3 py-2">
        <Sparkles size={14} className="text-brand-600" />
        <select
          className="ec-input h-8 max-w-[120px] py-0"
          value={provider}
          onChange={(e) => onProviderChange(e.target.value as AiProvider)}
        >
          {(Object.keys(PROVIDER_LABELS) as AiProvider[]).map((p) => (
            <option key={p} value={p}>{PROVIDER_LABELS[p]}</option>
          ))}
        </select>
        <select
          className="ec-input h-8 max-w-[200px] py-0"
          value={model}
          onChange={(e) => onModelChange(e.target.value)}
        >
          {(PROVIDER_MODELS[provider] || []).map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
        <span className="ml-auto text-[10px] uppercase tracking-wider text-ink-subtle">
          {apiKey ? 'BYO key' : 'server key'}
        </span>
        <button className="ec-btn-ghost px-2 py-1 text-xs" onClick={() => setHistory([])}>
          Clear
        </button>
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-auto p-3">
        {history.length === 0 && (
          <div className="space-y-3 text-sm">
            <p className="text-ink-muted">
              Pair-programming chat with {PROVIDER_LABELS[provider]} • {model}. Currently attached: <strong>{contextFiles.length}</strong> file(s).
            </p>
            <div className="flex flex-wrap gap-1">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="rounded-full border border-border bg-surface-muted px-2 py-1 text-xs hover:bg-surface-elevated"
                        onClick={() => setPrompt(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {history.map((m, i) => (
          <div key={i} className={cn(
            'rounded-lg border border-border p-3 text-sm',
            m.role === 'user' ? 'bg-brand-600/10 border-brand-600/20' : 'bg-surface-muted',
          )}>
            <div className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
              {m.role === 'user' ? <User2 size={11} /> : <Bot size={11} />}
              {m.role}
            </div>
            <div className="space-y-2">
              {blocks[i].map((b, j) => b.kind === 'text' ? (
                <p key={j} className="whitespace-pre-wrap leading-relaxed">{b.content}</p>
              ) : (
                <CodeBlock key={j} content={b.content} language={b.language || ''} onInsert={onInsert} />
              ))}
            </div>
          </div>
        ))}
        {send.isPending && (
          <div className="flex items-center gap-2 text-xs text-ink-muted">
            <Loader2 size={12} className="animate-spin" /> Thinking with {PROVIDER_LABELS[provider]}…
          </div>
        )}
      </div>

      <ContextChips
        files={contextFiles}
        tabs={tabs}
        onAdd={(p) => setContextFiles((prev) => prev.includes(p) ? prev : [...prev, p])}
        onRemove={(p) => setContextFiles((prev) => prev.filter((q) => q !== p))}
      />

      <footer className="shrink-0 border-t border-border p-2">
        <textarea
          className="ec-input min-h-[72px] resize-none font-sans text-sm"
          placeholder="Ask anything…   (⌘/Ctrl+Enter to send)"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && canSubmit) {
              e.preventDefault();
              send.mutate();
            }
          }}
        />
        <div className="mt-2 flex items-center justify-between">
          <span className="text-[10px] text-ink-subtle">
            {history.length} message{history.length === 1 ? '' : 's'}
          </span>
          <button
            className="ec-btn-primary"
            disabled={!canSubmit}
            onClick={() => send.mutate()}
          >
            {send.isPending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            Send
          </button>
        </div>
      </footer>
    </div>
  );
}

function ContextChips({
  files, tabs, onAdd, onRemove,
}: { files: string[]; tabs: EditorTab[]; onAdd: (p: string) => void; onRemove: (p: string) => void }) {
  const available = tabs.filter((t) => !files.includes(t.path));
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-1 border-t border-border bg-surface-muted px-2 py-1 text-[11px]">
      <span className="font-semibold text-ink-muted"><Paperclip size={10} className="inline" /> Context</span>
      {files.length === 0 && <span className="text-ink-subtle">none</span>}
      {files.map((f) => (
        <span key={f} className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-elevated px-2 py-0.5">
          <span className="max-w-[120px] truncate" title={f}>{baseName(f)}</span>
          <button onClick={() => onRemove(f)} className="opacity-70 hover:opacity-100"><X size={9} /></button>
        </span>
      ))}
      {available.length > 0 && (
        <select className="ec-input h-6 max-w-[120px] py-0 text-[11px]" value=""
                onChange={(e) => { if (e.target.value) onAdd(e.target.value); }}>
          <option value="">+ attach open file…</option>
          {available.map((t) => <option key={t.path} value={t.path}>{baseName(t.path)}</option>)}
        </select>
      )}
    </div>
  );
}

type Block = { kind: 'text' | 'code'; content: string; language?: string };

function splitCodeBlocks(text: string): Block[] {
  const out: Block[] = [];
  const re = /```([\w+-]*)\n([\s\S]*?)```/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push({ kind: 'text', content: text.slice(last, m.index).trim() });
    out.push({ kind: 'code', content: m[2].replace(/\n+$/, ''), language: m[1] });
    last = re.lastIndex;
  }
  if (last < text.length) out.push({ kind: 'text', content: text.slice(last).trim() });
  return out.filter((b) => b.content.length > 0);
}

function CodeBlock({ content, language, onInsert }: { content: string; language: string; onInsert: (c: string) => void }) {
  return (
    <div className="overflow-hidden rounded-md border border-border bg-zinc-950 text-zinc-100">
      <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-1 text-[10px] uppercase tracking-wider text-zinc-400">
        <span>{language || 'code'}</span>
        <div className="flex items-center gap-2">
          <button onClick={() => navigator.clipboard.writeText(content)} className="hover:text-white">Copy</button>
          <button onClick={() => onInsert(content)} className="text-brand-300 hover:text-brand-100">Insert →</button>
        </div>
      </div>
      <pre className="max-h-[320px] overflow-auto p-3 text-xs leading-snug"><code>{content}</code></pre>
    </div>
  );
}

function baseName(p: string): string {
  return p.split(/[/\\]/).pop() || p;
}
