import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowDownCircle, ArrowUpCircle, FilePlus, FileX, GitBranch, GitCommit, GitMerge, Loader2, Plus, RefreshCw, Square, SquareCheck } from 'lucide-react';
import toast from 'react-hot-toast';
import { cn, formatDateTime } from '../../../lib/utils';
import { MonacoView } from '../EditorTabs';
import {
  gitBranches, gitCheckout, gitCommit, gitDiff, gitInit, gitLog,
  gitPull, gitPush, gitStage, gitStatus, gitUnstage,
} from '../api';

type Props = { projectId: string | null; theme: 'vs-dark' | 'vs-light' };

export function GitPanel({ projectId, theme }: Props) {
  const qc = useQueryClient();
  const [message, setMessage] = useState('');
  const [diffPath, setDiffPath] = useState<{ path: string; staged: boolean } | null>(null);
  const [remote, setRemote] = useState('origin');

  const status = useQuery({
    enabled: !!projectId, queryKey: ['git-status', projectId],
    queryFn: () => gitStatus(projectId!),
    retry: false,
  });
  const log = useQuery({
    enabled: !!projectId && status.isSuccess, queryKey: ['git-log', projectId],
    queryFn: () => gitLog(projectId!, 30),
  });
  const branches = useQuery({
    enabled: !!projectId && status.isSuccess, queryKey: ['git-branches', projectId],
    queryFn: () => gitBranches(projectId!),
  });
  const diff = useQuery({
    enabled: !!projectId && !!diffPath, queryKey: ['git-diff', projectId, diffPath],
    queryFn: () => gitDiff(projectId!, diffPath?.path, diffPath?.staged ?? false),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['git-status', projectId] });
    qc.invalidateQueries({ queryKey: ['git-log', projectId] });
    qc.invalidateQueries({ queryKey: ['git-branches', projectId] });
    qc.invalidateQueries({ queryKey: ['git-diff', projectId] });
  };

  const stage = useMutation({
    mutationFn: (paths: string[]) => gitStage(projectId!, paths),
    onSuccess: invalidate,
  });
  const unstage = useMutation({
    mutationFn: (paths: string[]) => gitUnstage(projectId!, paths),
    onSuccess: invalidate,
  });
  const commit = useMutation({
    mutationFn: () => gitCommit(projectId!, message, false),
    onSuccess: () => { setMessage(''); invalidate(); toast.success('Committed'); },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Commit failed'),
  });
  const push = useMutation({
    mutationFn: () => gitPush(projectId!, remote),
    onSuccess: () => { invalidate(); toast.success('Pushed'); },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Push failed'),
  });
  const pull = useMutation({
    mutationFn: () => gitPull(projectId!, remote),
    onSuccess: () => { invalidate(); toast.success('Pulled'); },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Pull failed'),
  });
  const checkout = useMutation({
    mutationFn: (b: string) => gitCheckout(projectId!, b, false),
    onSuccess: () => { invalidate(); toast.success('Branch switched'); },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Checkout failed'),
  });
  const newBranch = useMutation({
    mutationFn: (b: string) => gitCheckout(projectId!, b, true),
    onSuccess: () => { invalidate(); toast.success('Branch created'); },
  });
  const initRepo = useMutation({
    mutationFn: () => gitInit(projectId!),
    onSuccess: () => { invalidate(); toast.success('Repository initialised'); },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'init failed'),
  });

  if (!projectId) return <PadEmpty>Select a project first.</PadEmpty>;
  if (status.isLoading) return <PadEmpty><Loader2 className="animate-spin" /></PadEmpty>;
  if (status.error) {
    return (
      <div className="p-4 text-sm text-ink-muted">
        <p>This project isn't a git repository yet.</p>
        <button className="ec-btn-primary mt-3" disabled={initRepo.isPending} onClick={() => initRepo.mutate()}>
          {initRepo.isPending ? 'Initialising…' : <>git init</>}
        </button>
      </div>
    );
  }

  const s = status.data!;
  const modifiedAll = [...new Set([...(s.modified || []), ...(s.untracked || [])])];

  return (
    <div className="flex h-full flex-col">
      <header className="shrink-0 space-y-2 border-b border-border bg-surface-muted p-3 text-xs">
        <div className="flex items-center gap-2">
          <GitBranch size={13} />
          <select
            className="ec-input h-7 max-w-[160px] py-0 text-xs"
            value={branches.data?.current || ''}
            onChange={(e) => checkout.mutate(e.target.value)}
          >
            {(branches.data?.local || []).map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
          <NewBranchButton onCreate={(b) => newBranch.mutate(b)} />
          <button className="ec-btn-ghost ml-auto px-2 py-0.5"
                  onClick={() => invalidate()} title="Refresh"><RefreshCw size={11} /></button>
        </div>
        <div className="flex items-center gap-2">
          <input className="ec-input h-7 max-w-[120px] py-0 text-xs" placeholder="remote"
                 value={remote} onChange={(e) => setRemote(e.target.value)} />
          <button className="ec-btn-secondary text-xs" disabled={push.isPending} onClick={() => push.mutate()}>
            <ArrowUpCircle size={11} /> Push {s.ahead > 0 && <span className="ec-badge bg-emerald-500/20 text-emerald-300">{s.ahead}</span>}
          </button>
          <button className="ec-btn-secondary text-xs" disabled={pull.isPending} onClick={() => pull.mutate()}>
            <ArrowDownCircle size={11} /> Pull {s.behind > 0 && <span className="ec-badge bg-amber-500/20 text-amber-300">{s.behind}</span>}
          </button>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-2 gap-2 overflow-hidden p-2">
        {/* Changes column */}
        <section className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-border">
          <h4 className="border-b border-border bg-surface-muted px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
            Changes ({modifiedAll.length} unstaged, {s.staged.length} staged)
          </h4>
          <div className="min-h-0 flex-1 space-y-2 overflow-auto p-2">
            <ChangeList
              title="Staged" entries={s.staged} staged
              onClick={(p) => setDiffPath({ path: p, staged: true })}
              onToggle={(p) => unstage.mutate([p])}
            />
            <ChangeList
              title="Modified" entries={s.modified}
              onClick={(p) => setDiffPath({ path: p, staged: false })}
              onToggle={(p) => stage.mutate([p])}
            />
            <UntrackedList
              entries={s.untracked}
              onAdd={(p) => stage.mutate([p])}
            />
          </div>
          <footer className="shrink-0 border-t border-border bg-surface-muted p-2">
            <textarea
              className="ec-input min-h-[60px] resize-none text-xs"
              placeholder="Commit message…"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
            <div className="mt-2 flex gap-2">
              <button className="ec-btn-secondary flex-1 text-xs"
                      disabled={s.modified.length + s.untracked.length === 0 || stage.isPending}
                      onClick={() => stage.mutate([...s.modified, ...s.untracked])}>
                Stage all
              </button>
              <button className="ec-btn-primary flex-1 text-xs"
                      disabled={!message.trim() || s.staged.length === 0 || commit.isPending}
                      onClick={() => commit.mutate()}>
                <GitCommit size={11} /> Commit ({s.staged.length})
              </button>
            </div>
          </footer>
        </section>

        {/* Right column: diff or log */}
        <section className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-border">
          {diffPath ? (
            <DiffPane diff={diff.data?.diff || ''} loading={diff.isFetching} theme={theme} onClose={() => setDiffPath(null)} path={diffPath.path} staged={diffPath.staged} />
          ) : (
            <LogPane commits={log.data?.commits || []} loading={log.isFetching} />
          )}
        </section>
      </div>
    </div>
  );
}

function NewBranchButton({ onCreate }: { onCreate: (name: string) => void }) {
  const [name, setName] = useState('');
  const [open, setOpen] = useState(false);
  if (!open) {
    return <button className="ec-btn-ghost px-2 py-0.5 text-xs" onClick={() => setOpen(true)}>
      <Plus size={11} /> New
    </button>;
  }
  return (
    <span className="flex items-center gap-1">
      <input autoFocus className="ec-input h-7 max-w-[120px] py-0 text-xs" placeholder="branch name"
             value={name} onChange={(e) => setName(e.target.value)}
             onKeyDown={(e) => { if (e.key === 'Enter' && name) { onCreate(name); setOpen(false); setName(''); } }} />
      <button className="ec-btn-primary text-[11px]" disabled={!name}
              onClick={() => { onCreate(name); setOpen(false); setName(''); }}>OK</button>
      <button className="ec-btn-ghost text-[11px]" onClick={() => { setOpen(false); setName(''); }}>×</button>
    </span>
  );
}

function ChangeList({
  title, entries, staged, onClick, onToggle,
}: {
  title: string; entries: string[]; staged?: boolean;
  onClick: (p: string) => void; onToggle: (p: string) => void;
}) {
  if (entries.length === 0) return null;
  return (
    <div>
      <p className="px-1 text-[10px] uppercase tracking-wider text-ink-muted">{title}</p>
      <ul className="space-y-0.5">
        {entries.map((p) => (
          <li key={p} className="group flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-surface-muted">
            <button onClick={() => onToggle(p)} className="text-ink-muted hover:text-ink"
                    title={staged ? 'Unstage' : 'Stage'}>
              {staged ? <SquareCheck size={11} /> : <Square size={11} />}
            </button>
            <button onClick={() => onClick(p)} className="flex-1 truncate text-left font-mono text-[11px]">{p}</button>
            <span className={cn('ec-badge text-[10px]', staged ? 'bg-emerald-500/20 text-emerald-300' : 'bg-amber-500/20 text-amber-300')}>
              {staged ? 'STAGED' : 'M'}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function UntrackedList({ entries, onAdd }: { entries: string[]; onAdd: (p: string) => void }) {
  if (entries.length === 0) return null;
  return (
    <div>
      <p className="px-1 text-[10px] uppercase tracking-wider text-ink-muted">Untracked</p>
      <ul className="space-y-0.5">
        {entries.map((p) => (
          <li key={p} className="flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-surface-muted">
            <button onClick={() => onAdd(p)} className="text-ink-muted hover:text-ink" title="Stage">
              <FilePlus size={11} />
            </button>
            <span className="flex-1 truncate font-mono text-[11px]">{p}</span>
            <span className="ec-badge bg-rose-500/20 text-rose-300 text-[10px]">NEW</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DiffPane({
  diff, loading, theme, onClose, path, staged,
}: { diff: string; loading: boolean; theme: 'vs-dark' | 'vs-light'; onClose: () => void; path: string; staged: boolean }) {
  return (
    <>
      <header className="flex shrink-0 items-center gap-2 border-b border-border bg-surface-muted px-3 py-1 text-[11px]">
        <span className="font-semibold">{staged ? '◉ STAGED' : '○ WORKING'} • {path}</span>
        <button className="ml-auto ec-btn-ghost px-2 py-0.5 text-[10px]" onClick={onClose}>Show log</button>
      </header>
      <div className="min-h-0 flex-1 overflow-hidden">
        {loading ? <div className="grid h-full place-items-center text-xs"><Loader2 className="animate-spin" /></div>
                 : <MonacoView value={diff || '(no changes)'} language="diff" theme={theme} readOnly height="100%" />}
      </div>
    </>
  );
}

function LogPane({ commits, loading }: { commits: { sha: string; full_sha: string; author: string; date: string; message: string }[]; loading: boolean }) {
  return (
    <>
      <header className="flex shrink-0 items-center border-b border-border bg-surface-muted px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
        <GitMerge size={11} className="mr-1" /> Recent commits
      </header>
      <div className="min-h-0 flex-1 overflow-auto p-2 text-xs">
        {loading && <Loader2 className="animate-spin" />}
        <ul className="space-y-1.5">
          {commits.map((c) => (
            <li key={c.full_sha} className="rounded border border-border p-2">
              <div className="flex items-center gap-2 text-[10px] text-ink-subtle">
                <code>{c.sha}</code>
                <span className="ml-auto">{formatDateTime(c.date)}</span>
              </div>
              <p className="mt-1 font-medium">{c.message}</p>
              <p className="text-[10px] text-ink-muted">{c.author}</p>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}

function PadEmpty({ children }: { children: React.ReactNode }) {
  return <div className="grid h-full place-items-center p-6 text-sm text-ink-muted">{children}</div>;
}
