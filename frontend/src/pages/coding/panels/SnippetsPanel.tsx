import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Globe, Library, Loader2, Pencil, Plus, Save, Search, Sparkles, Trash2, Wand2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { cn } from '../../../lib/utils';
import { MonacoView } from '../EditorTabs';
import {
  createSnippet, deleteSnippet, listSnippets, suggestSnippet, updateSnippet, useSnippet as useCount,
} from '../api';
import type { AiProvider, CodeSnippet } from '../types';

type Props = {
  onInsert: (code: string) => void;
  theme: 'vs-dark' | 'vs-light';
  provider: AiProvider;
  apiKey: string | null;
};

export function SnippetsPanel({ onInsert, theme, provider, apiKey }: Props) {
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [language, setLanguage] = useState('');
  const [editing, setEditing] = useState<CodeSnippet | 'new' | null>(null);

  const list = useQuery({
    queryKey: ['snippets', q, language],
    queryFn: () => listSnippets(q || undefined, language || undefined),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ['snippets'] });

  const remove = useMutation({
    mutationFn: (id: string) => deleteSnippet(id),
    onSuccess: invalidate,
  });

  const languages = useMemo(
    () => Array.from(new Set((list.data ?? []).map((s) => s.language))).sort(),
    [list.data],
  );

  if (editing) {
    return (
      <SnippetEditor
        snippet={editing === 'new' ? null : editing}
        theme={theme}
        provider={provider}
        apiKey={apiKey}
        onCancel={() => setEditing(null)}
        onSaved={() => { invalidate(); setEditing(null); }}
      />
    );
  }

  return (
    <div className="flex h-full flex-col">
      <header className="shrink-0 space-y-2 border-b border-border bg-surface-muted p-3">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <Library size={14} /> Snippet library
        </p>
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search size={11} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-ink-muted" />
            <input className="ec-input pl-7 text-xs" placeholder="Search snippets…"
                   value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className="ec-input max-w-[140px] text-xs" value={language}
                  onChange={(e) => setLanguage(e.target.value)}>
            <option value="">All languages</option>
            {languages.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
          <button className="ec-btn-primary text-xs" onClick={() => setEditing('new')}>
            <Plus size={11} /> New
          </button>
        </div>
      </header>
      <div className="min-h-0 flex-1 overflow-auto p-2">
        {list.isLoading && <Loader2 className="m-auto mt-6 block animate-spin" />}
        <ul className="space-y-2">
          {(list.data || []).map((s) => (
            <li key={s.id} className="rounded-lg border border-border bg-surface-elevated">
              <div className="flex items-center gap-2 p-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold">{s.title}</p>
                  <p className="truncate text-[11px] text-ink-muted">{s.description || '—'}</p>
                  <div className="mt-1 flex items-center gap-1 text-[10px]">
                    <span className="ec-badge bg-brand-500/15 text-brand-400">{s.language}</span>
                    {s.is_public && <span className="ec-badge bg-emerald-500/15 text-emerald-400"><Globe size={9} className="mr-0.5 inline" />public</span>}
                    <span className="text-ink-subtle">used {s.use_count}×</span>
                    {(s.tags || []).map((t) => (
                      <span key={t} className="ec-badge bg-surface-muted text-ink-muted">#{t}</span>
                    ))}
                  </div>
                </div>
                <button className="ec-btn-ghost p-1" onClick={() => setEditing(s)} title="Edit">
                  <Pencil size={11} />
                </button>
                <button className="ec-btn-ghost p-1 text-rose-500" onClick={() => remove.mutate(s.id)} title="Delete">
                  <Trash2 size={11} />
                </button>
              </div>
              <pre className="max-h-32 overflow-auto border-t border-border bg-zinc-950 px-3 py-2 text-[11px] text-zinc-100"><code>{s.code}</code></pre>
              <div className="flex items-center justify-end gap-2 border-t border-border px-2 py-1">
                <button className="ec-btn-ghost text-[11px]"
                        onClick={() => navigator.clipboard.writeText(s.code).then(() => toast.success('Copied'))}>
                  Copy
                </button>
                <button className="ec-btn-primary text-[11px]"
                        onClick={() => { useCount(s.id); onInsert(s.code); toast.success('Inserted'); invalidate(); }}>
                  Insert into editor
                </button>
              </div>
            </li>
          ))}
          {(list.data || []).length === 0 && !list.isLoading && (
            <li className="rounded-lg border border-dashed border-border p-6 text-center text-xs text-ink-muted">
              No snippets yet — create your first one or generate it with AI.
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}

function SnippetEditor({
  snippet, theme, provider, apiKey, onCancel, onSaved,
}: {
  snippet: CodeSnippet | null;
  theme: 'vs-dark' | 'vs-light';
  provider: AiProvider;
  apiKey: string | null;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(snippet?.title || '');
  const [language, setLanguage] = useState(snippet?.language || 'python');
  const [code, setCode] = useState(snippet?.code || '');
  const [description, setDescription] = useState(snippet?.description || '');
  const [tags, setTags] = useState((snippet?.tags || []).join(', '));
  const [isPublic, setIsPublic] = useState(snippet?.is_public ?? false);
  const [aiPrompt, setAiPrompt] = useState('');

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        title, language, code, description: description || null,
        tags: tags.split(',').map((t) => t.trim()).filter(Boolean),
        is_public: isPublic,
      } as any;
      return snippet ? updateSnippet(snippet.id, payload) : createSnippet(payload);
    },
    onSuccess: () => { toast.success('Saved'); onSaved(); },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Save failed'),
  });

  const suggest = useMutation({
    mutationFn: () => suggestSnippet({ description: aiPrompt, language, provider, api_key_override: apiKey }),
    onSuccess: (d) => {
      setTitle(d.title);
      setCode(d.code);
      setDescription(d.description);
      setLanguage(d.language || language);
      toast.success('AI suggestion ready');
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Suggestion failed'),
  });

  return (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 items-center gap-2 border-b border-border bg-surface-muted p-3">
        <p className="text-sm font-semibold">{snippet ? 'Edit snippet' : 'New snippet'}</p>
        <button className="ml-auto ec-btn-ghost text-xs" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary text-xs" disabled={!title.trim() || !code.trim() || save.isPending}
                onClick={() => save.mutate()}>
          {save.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
          Save
        </button>
      </header>
      <div className="min-h-0 flex-1 space-y-3 overflow-auto p-3">
        <div className="flex gap-2">
          <input className="ec-input flex-1" placeholder="Title" value={title}
                 onChange={(e) => setTitle(e.target.value)} />
          <input className="ec-input max-w-[140px]" placeholder="Language" value={language}
                 onChange={(e) => setLanguage(e.target.value)} />
        </div>
        <input className="ec-input" placeholder="Description (optional)" value={description}
               onChange={(e) => setDescription(e.target.value)} />
        <input className="ec-input" placeholder="Tags (comma-separated)" value={tags}
               onChange={(e) => setTags(e.target.value)} />
        <label className="flex items-center gap-2 text-xs">
          <input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} />
          Share with my team
        </label>
        <div className="overflow-hidden rounded-md border border-border">
          <MonacoView value={code} onChange={setCode} language={language} theme={theme} height="240px" />
        </div>
        <div className="rounded-lg border border-dashed border-border p-2">
          <p className="mb-1 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
            <Sparkles size={11} /> Generate with AI
          </p>
          <textarea className="ec-input min-h-[56px] text-xs" placeholder="e.g. 'Bash one-liner to fzf-select a git branch and check it out'"
                    value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)} />
          <button className="ec-btn-secondary mt-2 w-full text-xs" disabled={!aiPrompt.trim() || suggest.isPending}
                  onClick={() => suggest.mutate()}>
            {suggest.isPending ? <Loader2 size={12} className="animate-spin" /> : <Wand2 size={12} />}
            Suggest with {provider}
          </button>
        </div>
      </div>
    </div>
  );
}
