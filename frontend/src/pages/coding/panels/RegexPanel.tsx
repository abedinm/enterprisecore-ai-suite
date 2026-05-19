import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bookmark, Library, Loader2, Regex as RegexIcon, Sparkles, Trash2, Wand2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { cn } from '../../../lib/utils';
import {
  deleteRegexLibrary, listRegexLibrary, regexExplain, regexFromDescription,
  regexTest, saveRegexLibrary,
} from '../api';
import type { AiProvider, RegexLibraryEntry, RegexTestResult } from '../types';

type Props = { provider: AiProvider; apiKey: string | null };

export function RegexPanel({ provider, apiKey }: Props) {
  const qc = useQueryClient();
  const [pattern, setPattern] = useState('\\b\\d{3}-\\d{3}-\\d{4}\\b');
  const [flags, setFlags] = useState('');
  const [sample, setSample] = useState('Call us at 555-867-5309 or 800-555-0199.');
  const [replacement, setReplacement] = useState('');
  const [description, setDescription] = useState('');
  const [matchExamples, setMatchExamples] = useState('');
  const [noMatchExamples, setNoMatchExamples] = useState('');
  const [explain, setExplain] = useState<string>('');
  const [testCases, setTestCases] = useState<{ input: string; should_match: boolean; note?: string }[]>([]);
  const [result, setResult] = useState<RegexTestResult | null>(null);

  const lib = useQuery({ queryKey: ['regex-library'], queryFn: () => listRegexLibrary() });

  // Auto-test as user types
  const debounced = useDebouncedValue({ pattern, flags, sample, replacement }, 300);

  const test = useMutation({
    mutationFn: (p: typeof debounced) =>
      regexTest({ pattern: p.pattern, flags: p.flags, text: p.sample, replacement: p.replacement || undefined }),
    onSuccess: setResult,
  });

  useEffect(() => {
    if (debounced.pattern.trim()) test.mutate(debounced);
  }, [debounced.pattern, debounced.flags, debounced.sample, debounced.replacement]); // eslint-disable-line

  const explainAi = useMutation({
    mutationFn: () => regexExplain({ pattern, flags, provider, api_key_override: apiKey }),
    onSuccess: (d) => { setExplain(d.explanation); setTestCases(d.test_cases || []); },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Explain failed'),
  });

  const buildAi = useMutation({
    mutationFn: () => regexFromDescription({
      description,
      examples_match: matchExamples.split('\n').map((s) => s.trim()).filter(Boolean),
      examples_no_match: noMatchExamples.split('\n').map((s) => s.trim()).filter(Boolean),
      provider, api_key_override: apiKey,
    }),
    onSuccess: (d) => { setPattern(d.pattern); setFlags(d.flags); setExplain(d.explanation); toast.success('Pattern generated'); },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Build failed'),
  });

  const saveLib = useMutation({
    mutationFn: () => saveRegexLibrary({ title: pattern.slice(0, 40) || 'Untitled', pattern, flags, description: description || null, explanation: explain || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['regex-library'] }); toast.success('Saved to library'); },
  });

  const deleteLib = useMutation({
    mutationFn: (id: string) => deleteRegexLibrary(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['regex-library'] }),
  });

  const highlighted = useMemo(() => highlightMatches(sample, result?.matches || []), [sample, result]);

  return (
    <div className="grid h-full grid-cols-[1fr_220px] gap-2 p-2">
      <section className="flex min-h-0 flex-col overflow-auto rounded-lg border border-border p-3 space-y-3">
        <div>
          <div className="flex items-center gap-2">
            <RegexIcon size={12} />
            <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Pattern</p>
            <button className="ec-btn-ghost ml-auto px-2 py-0.5 text-[11px]" onClick={() => saveLib.mutate()}>
              <Bookmark size={11} /> Save to library
            </button>
          </div>
          <div className="mt-1 flex items-center gap-1 rounded-md border border-border bg-zinc-950 px-2 font-mono text-sm text-zinc-100">
            <span className="text-zinc-500">/</span>
            <input className="flex-1 bg-transparent px-1 py-2 outline-none" value={pattern}
                   onChange={(e) => setPattern(e.target.value)} />
            <span className="text-zinc-500">/</span>
            <input className="w-16 bg-transparent px-1 py-2 outline-none" placeholder="imsxua"
                   value={flags} onChange={(e) => setFlags(e.target.value.replace(/[^imsxua]/g, ''))} />
          </div>
          {result && !result.is_valid && (
            <p className="mt-1 text-[11px] text-rose-400">Invalid regex: {result.error}</p>
          )}
        </div>

        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Test string</p>
          <textarea className="ec-input mt-1 min-h-[120px] font-mono text-xs" value={sample}
                    onChange={(e) => setSample(e.target.value)} />
        </div>

        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Matches ({result?.matches.length ?? 0})</p>
          <div className="mt-1 max-h-32 overflow-auto rounded border border-border bg-surface-muted p-2 font-mono text-xs whitespace-pre-wrap">
            {highlighted}
          </div>
        </div>

        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Replace with</p>
          <input className="ec-input mt-1 font-mono text-xs"
                 placeholder="$1 (use back-references)" value={replacement}
                 onChange={(e) => setReplacement(e.target.value)} />
          {result?.replaced !== null && result?.replaced !== undefined && (
            <div className="mt-1 rounded border border-border bg-surface-muted p-2 font-mono text-xs whitespace-pre-wrap">{result.replaced}</div>
          )}
        </div>

        <div className="rounded-lg border border-dashed border-border p-3">
          <p className="mb-1 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
            <Sparkles size={11} /> AI assistant
          </p>
          <textarea className="ec-input min-h-[60px] text-xs" placeholder="Describe what you want to match…"
                    value={description} onChange={(e) => setDescription(e.target.value)} />
          <div className="mt-1 grid grid-cols-2 gap-2">
            <textarea className="ec-input min-h-[60px] font-mono text-xs"
                      placeholder="Examples that should match (one per line)"
                      value={matchExamples} onChange={(e) => setMatchExamples(e.target.value)} />
            <textarea className="ec-input min-h-[60px] font-mono text-xs"
                      placeholder="Examples that should NOT match"
                      value={noMatchExamples} onChange={(e) => setNoMatchExamples(e.target.value)} />
          </div>
          <div className="mt-2 flex gap-2">
            <button className="ec-btn-secondary flex-1 text-xs" disabled={!description.trim() || buildAi.isPending}
                    onClick={() => buildAi.mutate()}>
              {buildAi.isPending ? <Loader2 size={11} className="animate-spin" /> : <Wand2 size={11} />}
              Build regex from description
            </button>
            <button className="ec-btn-secondary flex-1 text-xs" disabled={!pattern.trim() || explainAi.isPending}
                    onClick={() => explainAi.mutate()}>
              {explainAi.isPending ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
              Explain current pattern
            </button>
          </div>
          {explain && (
            <article className="prose prose-sm dark:prose-invert mt-2 max-w-none whitespace-pre-wrap rounded bg-surface-muted p-2 text-[11px]">{explain}</article>
          )}
          {testCases.length > 0 && (
            <ul className="mt-2 space-y-1 text-[11px]">
              {testCases.map((t, i) => (
                <li key={i} className="flex items-center gap-2 rounded border border-border bg-surface-muted px-2 py-1">
                  <span className={cn('rounded px-1 text-[10px] font-bold',
                    t.should_match ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300')}>
                    {t.should_match ? 'MATCH' : 'NO MATCH'}
                  </span>
                  <code className="flex-1">{t.input}</code>
                  {t.note && <span className="text-ink-subtle">{t.note}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <aside className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-border">
        <header className="flex shrink-0 items-center gap-2 border-b border-border bg-surface-muted px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
          <Library size={11} /> Library
        </header>
        <ul className="min-h-0 flex-1 overflow-auto p-2">
          {(lib.data || []).map((e: RegexLibraryEntry) => (
            <li key={e.id} className="group mb-1 rounded border border-border bg-surface-muted p-2 text-[11px]">
              <div className="flex items-center gap-1">
                <button className="flex-1 truncate text-left font-semibold"
                        onClick={() => { setPattern(e.pattern); setFlags(e.flags); setExplain(e.explanation || ''); }}>
                  {e.title}
                </button>
                <button onClick={() => deleteLib.mutate(e.id)} className="opacity-0 group-hover:opacity-100 text-rose-500"><Trash2 size={10} /></button>
              </div>
              <p className="truncate font-mono text-[10px] text-ink-muted">/{e.pattern}/{e.flags}</p>
            </li>
          ))}
          {(lib.data || []).length === 0 && (
            <li className="p-3 text-[11px] text-ink-muted">Save common patterns to reuse them later.</li>
          )}
        </ul>
      </aside>
    </div>
  );
}

function useDebouncedValue<T>(value: T, delay: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [JSON.stringify(value), delay]); // eslint-disable-line
  return v;
}

function highlightMatches(text: string, matches: { start: number; end: number; match: string }[]): React.ReactNode {
  if (matches.length === 0) return text || <span className="text-ink-subtle">(no matches)</span>;
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  matches.forEach((m, i) => {
    if (m.start > cursor) parts.push(<span key={`t-${i}`}>{text.slice(cursor, m.start)}</span>);
    parts.push(<mark key={`m-${i}`} className="rounded bg-amber-500/30 px-0.5 text-amber-200">{text.slice(m.start, m.end)}</mark>);
    cursor = m.end;
  });
  if (cursor < text.length) parts.push(<span key="t-end">{text.slice(cursor)}</span>);
  return parts;
}
