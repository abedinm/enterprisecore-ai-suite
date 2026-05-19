import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { AlertTriangle, BookOpen, Bug, FileSearch, Loader2, Sparkles, Wand2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { cn } from '../../../lib/utils';
import { DiffViewer, MonacoView } from '../EditorTabs';
import { aiBugfix, aiDocstring, aiExplain, aiGenerate, aiReview } from '../api';
import type { AiProvider, EditorTab, ReviewFinding } from '../types';

type Theme = 'vs-dark' | 'vs-light';
type Mode = 'generate' | 'explain' | 'docstring' | 'bugfix' | 'review';

type Props = {
  activeTab: EditorTab | null;
  selection: string;
  provider: AiProvider;
  model: string;
  apiKey: string | null;
  theme: Theme;
  onApply: (newContent: string) => void;
  onInsert: (snippet: string) => void;
  projectId: string | null;
  contextFiles: string[];
};

export function CodeToolsPanel(p: Props) {
  const [mode, setMode] = useState<Mode>('generate');
  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 overflow-x-auto border-b border-border bg-surface-muted">
        <Tab icon={Sparkles} label="Generate" active={mode === 'generate'} onClick={() => setMode('generate')} />
        <Tab icon={BookOpen} label="Explain" active={mode === 'explain'} onClick={() => setMode('explain')} />
        <Tab icon={Wand2} label="Docs" active={mode === 'docstring'} onClick={() => setMode('docstring')} />
        <Tab icon={Bug} label="Bug Fix" active={mode === 'bugfix'} onClick={() => setMode('bugfix')} />
        <Tab icon={FileSearch} label="Review" active={mode === 'review'} onClick={() => setMode('review')} />
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {mode === 'generate' && <Generate {...p} />}
        {mode === 'explain' && <Explain {...p} />}
        {mode === 'docstring' && <Docstring {...p} />}
        {mode === 'bugfix' && <BugFix {...p} />}
        {mode === 'review' && <Review {...p} />}
      </div>
    </div>
  );
}

function Tab({ icon: Icon, label, active, onClick }: {
  icon: any; label: string; active: boolean; onClick: () => void;
}) {
  return (
    <button onClick={onClick} className={cn(
      'flex items-center gap-1 border-r border-border px-3 py-2 text-xs last:border-r-0',
      active ? 'bg-surface-elevated font-semibold text-brand-600' : 'text-ink-muted hover:bg-surface-elevated',
    )}>
      <Icon size={11} /> {label}
    </button>
  );
}

// ---- Generate -----------------------------------------------------------
function Generate({ provider, model, apiKey, projectId, contextFiles, onInsert, theme, activeTab }: Props) {
  const [prompt, setPrompt] = useState('');
  const [language, setLanguage] = useState(activeTab?.language || 'python');
  const [result, setResult] = useState<{ code: string; explanation: string; provider: string; model: string } | null>(null);

  const run = useMutation({
    mutationFn: () => aiGenerate({
      prompt, language, project_id: projectId ?? undefined,
      context_files: contextFiles, provider, model, api_key_override: apiKey,
    }),
    onSuccess: setResult,
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Generation failed'),
  });

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <input className="ec-input flex-1" placeholder="Language (e.g. python, typescript, rust)"
               value={language} onChange={(e) => setLanguage(e.target.value)} />
      </div>
      <textarea className="ec-input min-h-[100px] font-sans" placeholder="Describe what to build in plain English…"
                value={prompt} onChange={(e) => setPrompt(e.target.value)} />
      <button className="ec-btn-primary w-full" disabled={!prompt.trim() || run.isPending}
              onClick={() => run.mutate()}>
        {run.isPending ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
        Generate
      </button>
      {result && (
        <div className="space-y-2">
          <div className="overflow-hidden rounded-md border border-border">
            <MonacoView value={result.code} language={language} theme={theme} readOnly height="260px" />
          </div>
          <div className="flex gap-2">
            <button className="ec-btn-secondary flex-1 text-xs" onClick={() => navigator.clipboard.writeText(result.code).then(() => toast.success('Copied'))}>Copy</button>
            <button className="ec-btn-primary flex-1 text-xs" onClick={() => onInsert(result.code)}>Insert into editor</button>
          </div>
          {result.explanation && (
            <p className="rounded-lg bg-surface-muted p-3 text-xs leading-relaxed text-ink-muted">{result.explanation}</p>
          )}
          <p className="text-[10px] text-ink-subtle">{result.provider} • {result.model}</p>
        </div>
      )}
    </div>
  );
}

// ---- Explain ------------------------------------------------------------
function Explain({ activeTab, selection, provider, model, apiKey }: Props) {
  const [result, setResult] = useState<string>('');
  const codeIn = selection.trim() ? selection : activeTab?.current || '';
  const language = activeTab?.language || 'plaintext';
  const run = useMutation({
    mutationFn: () => aiExplain({ code: codeIn, language, provider, model, api_key_override: apiKey }),
    onSuccess: (d) => setResult(d.explanation),
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Explain failed'),
  });
  return (
    <div className="space-y-3">
      <p className="text-xs text-ink-muted">
        Explains your {selection.trim() ? 'current selection' : 'active file'}. Switch focus to a tab in the editor to change the input.
      </p>
      <button className="ec-btn-primary w-full" disabled={!codeIn.trim() || run.isPending}
              onClick={() => run.mutate()}>
        {run.isPending ? <Loader2 size={14} className="animate-spin" /> : <BookOpen size={14} />}
        Explain {selection.trim() ? 'selection' : 'this file'}
      </button>
      {result && (
        <article className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap rounded-lg bg-surface-muted p-3 text-sm leading-relaxed">
          {result}
        </article>
      )}
    </div>
  );
}

// ---- Docstring ----------------------------------------------------------
function Docstring({ activeTab, provider, model, apiKey, onApply, theme }: Props) {
  const [style, setStyle] = useState<'google' | 'numpy' | 'sphinx' | 'jsdoc'>('google');
  const [result, setResult] = useState<string>('');
  const language = activeTab?.language || 'plaintext';
  const code = activeTab?.current || '';
  const run = useMutation({
    mutationFn: () => aiDocstring({ code, language, style, provider, model, api_key_override: apiKey }),
    onSuccess: (d) => setResult(d.documented_code),
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Docstring generation failed'),
  });
  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <select className="ec-input" value={style} onChange={(e) => setStyle(e.target.value as any)}>
          <option value="google">Google</option>
          <option value="numpy">NumPy</option>
          <option value="sphinx">Sphinx</option>
          <option value="jsdoc">JSDoc</option>
        </select>
        <button className="ec-btn-primary flex-1" disabled={!code.trim() || run.isPending}
                onClick={() => run.mutate()}>
          {run.isPending ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />}
          Generate docs for this file
        </button>
      </div>
      {result && (
        <div className="space-y-2">
          <p className="text-[11px] uppercase tracking-wider text-ink-muted">Preview (original ↔ documented)</p>
          <div className="overflow-hidden rounded-md border border-border" style={{ height: 320 }}>
            <DiffViewer original={code} modified={result} language={language} theme={theme} />
          </div>
          <div className="flex gap-2">
            <button className="ec-btn-secondary flex-1" onClick={() => navigator.clipboard.writeText(result).then(() => toast.success('Copied'))}>Copy</button>
            <button className="ec-btn-primary flex-1" onClick={() => { onApply(result); toast.success('Applied to editor'); }}>Apply to file</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---- Bug Fix ------------------------------------------------------------
function BugFix({ activeTab, provider, model, apiKey, onApply, theme }: Props) {
  const [error, setError] = useState('');
  const [result, setResult] = useState<{ fixed_code: string; explanation: string } | null>(null);
  const language = activeTab?.language || 'plaintext';
  const code = activeTab?.current || '';
  const run = useMutation({
    mutationFn: () => aiBugfix({ code, error, language, provider, model, api_key_override: apiKey }),
    onSuccess: setResult,
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Bug fix failed'),
  });
  return (
    <div className="space-y-3">
      <textarea className="ec-input min-h-[60px] font-mono text-xs"
                placeholder="Paste the error / stack trace (optional but improves accuracy)"
                value={error} onChange={(e) => setError(e.target.value)} />
      <button className="ec-btn-primary w-full" disabled={!code.trim() || run.isPending}
              onClick={() => run.mutate()}>
        {run.isPending ? <Loader2 size={14} className="animate-spin" /> : <Bug size={14} />}
        Detect & fix bugs in this file
      </button>
      {result && (
        <div className="space-y-2">
          <p className="text-[11px] uppercase tracking-wider text-ink-muted">Proposed fix</p>
          <div className="overflow-hidden rounded-md border border-border" style={{ height: 320 }}>
            <DiffViewer original={code} modified={result.fixed_code} language={language} theme={theme} />
          </div>
          {result.explanation && (
            <p className="rounded-lg bg-surface-muted p-3 text-xs leading-relaxed">{result.explanation}</p>
          )}
          <div className="flex gap-2">
            <button className="ec-btn-secondary flex-1" onClick={() => navigator.clipboard.writeText(result.fixed_code).then(() => toast.success('Copied'))}>Copy</button>
            <button className="ec-btn-primary flex-1" onClick={() => { onApply(result.fixed_code); toast.success('Applied'); }}>Apply fix</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---- Review -------------------------------------------------------------
function Review({ activeTab, provider, model, apiKey }: Props) {
  const [focus, setFocus] = useState('security, correctness, performance');
  const [result, setResult] = useState<{ summary: string; findings: ReviewFinding[] } | null>(null);
  const language = activeTab?.language || 'plaintext';
  const code = activeTab?.current || '';
  const run = useMutation({
    mutationFn: () => aiReview({ code, language, focus, provider, model, api_key_override: apiKey }),
    onSuccess: setResult,
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Review failed'),
  });
  return (
    <div className="space-y-3">
      <input className="ec-input" placeholder="Review focus (security, performance, style, design…)"
             value={focus} onChange={(e) => setFocus(e.target.value)} />
      <button className="ec-btn-primary w-full" disabled={!code.trim() || run.isPending}
              onClick={() => run.mutate()}>
        {run.isPending ? <Loader2 size={14} className="animate-spin" /> : <FileSearch size={14} />}
        Run AI code review
      </button>
      {result && (
        <div className="space-y-2 text-sm">
          {result.summary && <p className="rounded-lg bg-surface-muted p-3 leading-relaxed">{result.summary}</p>}
          {result.findings.length === 0 ? (
            <p className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-600 dark:text-emerald-400">
              No findings. The reviewer didn't flag anything.
            </p>
          ) : result.findings.map((f, i) => (
            <FindingCard key={i} f={f} />
          ))}
        </div>
      )}
    </div>
  );
}

function FindingCard({ f }: { f: ReviewFinding }) {
  const sev = (f.severity || 'medium').toLowerCase();
  const color = sev === 'high' ? 'border-rose-500/40 bg-rose-500/10'
              : sev === 'medium' ? 'border-amber-500/40 bg-amber-500/10'
              : 'border-emerald-500/40 bg-emerald-500/10';
  return (
    <div className={cn('rounded-lg border p-3 text-xs', color)}>
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1 font-semibold uppercase tracking-wider">
          <AlertTriangle size={11} /> {sev} • {f.category}
        </span>
        {f.line != null && <span className="rounded bg-surface-elevated px-1.5 py-0.5">line {f.line}</span>}
      </div>
      <p className="mt-1 font-medium">{f.message}</p>
      {f.suggestion && <p className="mt-1 text-ink-muted">→ {f.suggestion}</p>}
    </div>
  );
}
