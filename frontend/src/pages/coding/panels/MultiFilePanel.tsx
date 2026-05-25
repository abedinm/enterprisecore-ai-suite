import { useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Boxes, Check, FilePlus2, Loader2, Wand2, X } from 'lucide-react';
import toast from 'react-hot-toast';
import { cn } from '../../../lib/utils';
import { DiffViewer } from '../EditorTabs';
import { applyMultiFile, planMultiFile, readFile } from '../api';
import { useFileSearch } from '../FileTree';
import type { AiProvider, FileNode, FilePatchOp, MultiFileEditResponse } from '../types';

type Props = {
  projectId: string | null;
  tree: FileNode | null;
  provider: AiProvider;
  apiKey: string | null;
  theme: 'vs-dark' | 'vs-light';
  onRefreshTree: () => void;
};

export function MultiFilePanel({ projectId, tree, theme, onRefreshTree }: Props) {
  const [prompt, setPrompt] = useState('');
  const [contextFiles, setContextFiles] = useState<string[]>([]);
  const [targetFiles, setTargetFiles] = useState<string[]>([]);
  const [plan, setPlan] = useState<MultiFileEditResponse | null>(null);
  const [originals, setOriginals] = useState<Record<string, string>>({});
  const [picker, setPicker] = useState<'context' | 'target' | null>(null);
  const [pickerQuery, setPickerQuery] = useState('');
  const [selected, setSelected] = useState<Record<string, boolean>>({});

  const { all, search } = useFileSearch(tree);
  const searched = useMemo(() => search(pickerQuery, 50), [search, pickerQuery]);

  const run = useMutation({
    mutationFn: () => planMultiFile({
      project_id: projectId!,
      prompt,
      context_files: contextFiles,
      target_files: targetFiles,
    }),
    onSuccess: async (data) => {
      // Pre-fetch originals for each changed file so we can show side-by-side diffs
      const origs: Record<string, string> = {};
      const sel: Record<string, boolean> = {};
      await Promise.all(data.changes.map(async (c) => {
        sel[c.path] = true;
        try {
          const file = await readFile(projectId!, c.path);
          origs[c.path] = file.content;
        } catch {
          origs[c.path] = '';
        }
      }));
      setPlan(data);
      setOriginals(origs);
      setSelected(sel);
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Planning failed'),
  });

  const apply = useMutation({
    mutationFn: () => applyMultiFile(projectId!, plan!.changes.filter((c) => selected[c.path])),
    onSuccess: (d) => {
      toast.success(`Applied ${d.count} file change${d.count === 1 ? '' : 's'}`);
      setPlan(null);
      setOriginals({});
      onRefreshTree();
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Apply failed'),
  });

  if (!projectId) return <Empty>Select a project first.</Empty>;

  return (
    <div className="flex h-full flex-col">
      <header className="shrink-0 space-y-2 border-b border-border bg-surface-muted p-3">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <Boxes size={14} /> Multi-file AI edit
        </p>
        <p className="text-[11px] text-ink-muted">
          The AI reads your <em>context files</em> (read-only background) and proposes complete new contents for the <em>target files</em>. Preview every diff before applying.
        </p>
      </header>

      {!plan && (
        <div className="min-h-0 flex-1 space-y-3 overflow-auto p-3">
          <textarea
            className="ec-input min-h-[100px] font-sans text-sm"
            placeholder="Describe the change. E.g. 'Add a /healthz route in routes/health.py, register it in app.py, and update tests/test_health.py.'"
            value={prompt} onChange={(e) => setPrompt(e.target.value)}
          />
          <PickerSection label="Context (read-only)" files={contextFiles}
                         onAdd={() => setPicker('context')}
                         onRemove={(p) => setContextFiles((x) => x.filter((q) => q !== p))} />
          <PickerSection label="Targets (may be edited)" files={targetFiles}
                         onAdd={() => setPicker('target')}
                         onRemove={(p) => setTargetFiles((x) => x.filter((q) => q !== p))} />
          <button className="ec-btn-primary w-full"
                  disabled={!prompt.trim() || targetFiles.length === 0 || run.isPending}
                  onClick={() => run.mutate()}>
            {run.isPending ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />}
            Plan multi-file change
          </button>
          <p className="text-[10px] text-ink-subtle">
            Tip: targets can include files that don't exist yet — the AI will create them.
          </p>
        </div>
      )}

      {plan && (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className="shrink-0 border-b border-border bg-surface-muted p-3">
            <p className="text-sm font-medium">{plan.summary}</p>
            <p className="mt-1 text-[10px] text-ink-subtle">{plan.provider} • {plan.model} • {plan.changes.length} file change(s)</p>
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-2">
            <ul className="space-y-2">
              {plan.changes.map((c) => (
                <DiffCard key={c.path} change={c} original={originals[c.path] || ''}
                          selected={selected[c.path]}
                          onToggle={() => setSelected((s) => ({ ...s, [c.path]: !s[c.path] }))}
                          theme={theme} />
              ))}
            </ul>
          </div>
          <footer className="flex shrink-0 items-center gap-2 border-t border-border bg-surface-muted p-3">
            <button className="ec-btn-ghost text-xs" onClick={() => setPlan(null)}>Back</button>
            <span className="ml-auto text-xs text-ink-muted">
              {Object.values(selected).filter(Boolean).length} of {plan.changes.length} selected
            </span>
            <button className="ec-btn-primary text-xs" disabled={apply.isPending}
                    onClick={() => apply.mutate()}>
              {apply.isPending ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
              Apply selected
            </button>
          </footer>
        </div>
      )}

      {picker && (
        <div role="presentation" className="absolute inset-0 z-30 flex items-start justify-center bg-black/40 p-12" onClick={() => setPicker(null)}>
          <div className="w-full max-w-2xl rounded-lg border border-border bg-surface-elevated p-3 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <p className="mb-2 text-sm font-semibold">Select files for <em>{picker}</em></p>
            <input autoFocus className="ec-input" placeholder="Filter…" value={pickerQuery}
                   onChange={(e) => setPickerQuery(e.target.value)} />
            <ul className="mt-2 max-h-80 space-y-0.5 overflow-auto rounded border border-border">
              {searched.map((path) => {
                const targetList = picker === 'context' ? contextFiles : targetFiles;
                const setList = picker === 'context' ? setContextFiles : setTargetFiles;
                const checked = targetList.includes(path);
                return (
                  <li key={path}>
                    <label className="flex cursor-pointer items-center gap-2 px-3 py-1 text-xs hover:bg-surface-muted">
                      <input type="checkbox" checked={checked} onChange={() => {
                        setList((prev) => checked ? prev.filter((p) => p !== path) : [...prev, path]);
                      }} />
                      <span className="truncate font-mono">{path}</span>
                    </label>
                  </li>
                );
              })}
              {searched.length === 0 && <li className="p-3 text-xs text-ink-muted">No files match.</li>}
            </ul>
            <div className="mt-2 flex items-center justify-between">
              <p className="text-[10px] text-ink-subtle">{all.length} files in project</p>
              <button className="ec-btn-primary text-xs" onClick={() => setPicker(null)}>Done</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function PickerSection({
  label, files, onAdd, onRemove,
}: { label: string; files: string[]; onAdd: () => void; onRemove: (p: string) => void }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">{label}</p>
        <button className="ec-btn-ghost px-2 py-0.5 text-[11px]" onClick={onAdd}>
          <FilePlus2 size={11} /> Add files
        </button>
      </div>
      {files.length === 0 ? (
        <p className="text-[11px] text-ink-subtle">No files selected</p>
      ) : (
        <ul className="space-y-0.5">
          {files.map((p) => (
            <li key={p} className="flex items-center gap-2 rounded bg-surface-muted px-2 py-1 text-[11px]">
              <span className="flex-1 truncate font-mono">{p}</span>
              <button onClick={() => onRemove(p)}><X size={11} /></button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function DiffCard({
  change, original, selected, onToggle, theme,
}: {
  change: FilePatchOp;
  original: string;
  selected: boolean;
  onToggle: () => void;
  theme: 'vs-dark' | 'vs-light';
}) {
  const [expanded, setExpanded] = useState(true);
  const isNew = !original;
  return (
    <li className={cn('overflow-hidden rounded-lg border', selected ? 'border-brand-500/40' : 'border-border')}>
      <header className="flex items-center gap-2 bg-surface-muted px-3 py-2 text-xs">
        <input type="checkbox" checked={selected} onChange={onToggle} />
        <span className={cn('font-mono', isNew && 'text-emerald-400')}>{change.path}</span>
        {isNew && <span className="ec-badge bg-emerald-500/20 text-emerald-300">NEW</span>}
        <button className="ml-auto ec-btn-ghost px-2 py-0.5 text-[11px]" onClick={() => setExpanded((v) => !v)}>
          {expanded ? 'Collapse' : 'Show diff'}
        </button>
      </header>
      {expanded && (
        <div style={{ height: 280 }} className="border-t border-border">
          <DiffViewer original={original} modified={change.content} language={guessLanguage(change.path)} theme={theme} />
        </div>
      )}
    </li>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="grid h-full place-items-center p-6 text-sm text-ink-muted">{children}</div>;
}

function guessLanguage(path: string): string {
  const ext = path.match(/\.([^.\/\\]+)$/)?.[1].toLowerCase() || '';
  return ({
    py: 'python', js: 'javascript', mjs: 'javascript', cjs: 'javascript',
    ts: 'typescript', tsx: 'typescript', jsx: 'javascript',
    json: 'json', html: 'html', css: 'css', md: 'markdown',
    sh: 'shell', ps1: 'powershell', sql: 'sql', go: 'go', rs: 'rust',
    yml: 'yaml', yaml: 'yaml', toml: 'toml',
  } as Record<string, string>)[ext] || 'plaintext';
}
