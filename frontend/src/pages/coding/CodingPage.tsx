import { useEffect, useState } from 'react';
import { Folder, FolderOpen, FileText, Save, Plus, GitBranch, Terminal as TermIcon, Sparkles, Wrench, Search, Database } from 'lucide-react';
import Editor from '@monaco-editor/react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../lib/api';
import { cn } from '../../lib/utils';

type CodeProject = { id: string; name: string; path: string; is_git: boolean; language_primary: string | null };
type FileNode = { name: string; path: string; is_dir: boolean; size: number | null; children?: FileNode[] };
type FileContent = { path: string; content: string; language: string | null };

export function CodingPage() {
  const qc = useQueryClient();
  const [projectId, setProjectId] = useState<string | null>(null);
  const [openPath, setOpenPath] = useState<string | null>(null);
  const [editorValue, setEditorValue] = useState('');
  const [editorLanguage, setEditorLanguage] = useState<string>('plaintext');
  const [rightPanel, setRightPanel] = useState<'chat' | 'terminal' | 'review' | 'git'>('chat');
  const [showNewProject, setShowNewProject] = useState(false);

  const projects = useQuery({
    queryKey: ['coding', 'projects'],
    queryFn: async () => (await api.get<CodeProject[]>('/coding/projects')).data,
  });

  useEffect(() => {
    if (!projectId && projects.data?.length) setProjectId(projects.data[0].id);
  }, [projects.data, projectId]);

  const tree = useQuery({
    enabled: !!projectId,
    queryKey: ['coding', 'tree', projectId],
    queryFn: async () => (await api.get<FileNode>('/coding/tree', { params: { project_id: projectId, depth: 3 } })).data,
  });

  const fileQuery = useQuery({
    enabled: !!projectId && !!openPath,
    queryKey: ['coding', 'file', projectId, openPath],
    queryFn: async () => (await api.get<FileContent>('/coding/file', { params: { project_id: projectId, path: openPath } })).data,
  });

  useEffect(() => {
    if (fileQuery.data) {
      setEditorValue(fileQuery.data.content);
      setEditorLanguage(fileQuery.data.language || 'plaintext');
    }
  }, [fileQuery.data]);

  const saveFile = useMutation({
    mutationFn: async () => (await api.post('/coding/file', { path: openPath, content: editorValue }, { params: { project_id: projectId } })).data,
  });

  return (
    <div className="flex h-[calc(100vh-9rem)] gap-3">
      <aside className="flex w-64 shrink-0 flex-col rounded-xl border border-border bg-surface-elevated">
        <div className="flex items-center justify-between border-b border-border p-3">
          <p className="text-sm font-semibold">Projects</p>
          <button className="ec-btn-ghost" title="New project" onClick={() => setShowNewProject((v) => !v)}><Plus size={16} /></button>
        </div>
        {showNewProject && <NewProjectForm onSaved={() => { setShowNewProject(false); qc.invalidateQueries({ queryKey: ['coding', 'projects'] }); }} />}
        <div className="flex-1 overflow-auto p-2">
          <ul className="space-y-1">
            {projects.data?.map((p) => (
              <li key={p.id}>
                <button
                  className={cn('flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm',
                    projectId === p.id ? 'bg-brand-600 text-white' : 'hover:bg-surface-muted')}
                  onClick={() => { setProjectId(p.id); setOpenPath(null); }}
                >
                  {projectId === p.id ? <FolderOpen size={14} /> : <Folder size={14} />}
                  <span className="truncate">{p.name}</span>
                  {p.is_git && <GitBranch size={12} className="opacity-60" />}
                </button>
              </li>
            ))}
          </ul>
          {tree.data && (
            <div className="mt-3 border-t border-border pt-3">
              <p className="px-2 pb-1 text-xs uppercase tracking-wider text-ink-muted">Files</p>
              <FileTree node={tree.data} depth={0} onOpen={setOpenPath} active={openPath} />
            </div>
          )}
        </div>
      </aside>

      <main className="flex flex-1 flex-col rounded-xl border border-border bg-surface-elevated overflow-hidden">
        <div className="flex items-center justify-between border-b border-border bg-surface-muted px-3 py-2">
          <div className="flex items-center gap-2">
            <FileText size={14} className="text-ink-muted" />
            <span className="text-sm font-medium">{openPath ?? 'No file open'}</span>
            <span className="text-xs text-ink-subtle">{editorLanguage}</span>
          </div>
          <button className="ec-btn-primary" disabled={!openPath || saveFile.isPending} onClick={() => saveFile.mutate()}>
            <Save size={14} /> {saveFile.isPending ? 'Saving…' : 'Save'}
          </button>
        </div>
        <div className="flex-1 min-h-0">
          {openPath ? (
            <Editor
              height="100%"
              theme="vs-dark"
              language={editorLanguage}
              value={editorValue}
              onChange={(v) => setEditorValue(v ?? '')}
              options={{ minimap: { enabled: false }, fontSize: 13, wordWrap: 'on', tabSize: 2 }}
            />
          ) : (
            <div className="grid h-full place-items-center text-sm text-ink-muted">
              Open a file from the tree to start editing.
            </div>
          )}
        </div>
      </main>

      <section className="flex w-96 shrink-0 flex-col rounded-xl border border-border bg-surface-elevated overflow-hidden">
        <div className="flex border-b border-border bg-surface-muted">
          <TabBtn icon={Sparkles} label="AI" active={rightPanel === 'chat'} onClick={() => setRightPanel('chat')} />
          <TabBtn icon={Wrench} label="Review" active={rightPanel === 'review'} onClick={() => setRightPanel('review')} />
          <TabBtn icon={TermIcon} label="Terminal" active={rightPanel === 'terminal'} onClick={() => setRightPanel('terminal')} />
          <TabBtn icon={GitBranch} label="Git" active={rightPanel === 'git'} onClick={() => setRightPanel('git')} />
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-3">
          {rightPanel === 'chat' && <AIChatPanel projectId={projectId} openPath={openPath} setEditorValue={setEditorValue} />}
          {rightPanel === 'review' && <CodeReviewPanel code={editorValue} language={editorLanguage} />}
          {rightPanel === 'terminal' && <TerminalPanel projectId={projectId} />}
          {rightPanel === 'git' && <GitPanel projectId={projectId} />}
        </div>
      </section>
    </div>
  );
}

function NewProjectForm({ onSaved }: { onSaved: () => void }) {
  const [name, setName] = useState('');
  const [path, setPath] = useState('');
  const save = useMutation({
    mutationFn: async () => (await api.post('/coding/projects', { name, path })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="border-b border-border p-3 space-y-2">
      <input className="ec-input" placeholder="Project name" value={name} onChange={(e) => setName(e.target.value)} />
      <input className="ec-input" placeholder="Absolute path (e.g. F:/code/myproj)" value={path} onChange={(e) => setPath(e.target.value)} />
      <button className="ec-btn-primary w-full" disabled={!name || !path || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Creating…' : 'Add project'}</button>
    </div>
  );
}

function FileTree({ node, depth, onOpen, active }: { node: FileNode; depth: number; onOpen: (p: string) => void; active: string | null }) {
  const [open, setOpen] = useState(depth < 2);
  if (node.is_dir) {
    return (
      <div>
        <button className="flex w-full items-center gap-1 rounded px-2 py-1 text-left text-sm hover:bg-surface-muted" onClick={() => setOpen((v) => !v)}>
          {open ? <FolderOpen size={12} /> : <Folder size={12} />}
          <span className="truncate">{node.name || node.path}</span>
        </button>
        {open && node.children && (
          <ul className="ml-3 border-l border-border pl-2">
            {node.children.map((c) => <li key={c.path}><FileTree node={c} depth={depth + 1} onOpen={onOpen} active={active} /></li>)}
          </ul>
        )}
      </div>
    );
  }
  return (
    <button
      className={cn('flex w-full items-center gap-1 rounded px-2 py-1 text-left text-sm',
        active === node.path ? 'bg-brand-600 text-white' : 'hover:bg-surface-muted')}
      onClick={() => onOpen(node.path)}
    >
      <FileText size={12} />
      <span className="truncate">{node.name}</span>
    </button>
  );
}

function TabBtn({ icon: Icon, label, active, onClick }: { icon: any; label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className={cn('flex flex-1 items-center justify-center gap-1 border-r border-border px-3 py-2 text-sm last:border-r-0',
      active ? 'bg-surface-elevated font-semibold text-brand-600' : 'text-ink-muted hover:bg-surface-elevated')}>
      <Icon size={14} /> {label}
    </button>
  );
}

function AIChatPanel({ projectId, openPath, setEditorValue }: { projectId: string | null; openPath: string | null; setEditorValue: (v: string) => void }) {
  const [prompt, setPrompt] = useState('');
  const [history, setHistory] = useState<{ role: string; content: string }[]>([]);
  const send = useMutation({
    mutationFn: async () => (await api.post('/ai/chat', {
      messages: [...history, { role: 'user', content: prompt }],
      feature: 'coding_chat', max_tokens: 1200,
    })).data,
    onSuccess: (data) => {
      setHistory([...history, { role: 'user', content: prompt }, { role: 'assistant', content: data.text }]);
      setPrompt('');
    },
  });
  const generate = useMutation({
    mutationFn: async () => (await api.post('/coding/ai/generate', {
      prompt, project_id: projectId, context_files: openPath ? [openPath] : undefined,
    })).data,
    onSuccess: (data) => {
      setHistory([...history, { role: 'user', content: prompt }, { role: 'assistant', content: '```\n' + data.code + '\n```\n' + data.explanation }]);
      setPrompt('');
    },
  });

  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex-1 space-y-2 overflow-auto">
        {history.length === 0 && (
          <p className="text-sm text-ink-muted">Ask anything. The current file is included as context. Try: <em>"explain the structure of this file"</em> or <em>"generate a unit test"</em>.</p>
        )}
        {history.map((m, i) => (
          <div key={i} className={cn('rounded-lg p-3 text-sm',
            m.role === 'user' ? 'bg-brand-50 dark:bg-brand-900/20' : 'bg-surface-muted')}>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink-muted">{m.role}</p>
            <pre className="whitespace-pre-wrap font-sans">{m.content}</pre>
            {m.role === 'assistant' && m.content.includes('```') && (
              <button className="mt-2 ec-btn-ghost text-xs" onClick={() => {
                const match = m.content.match(/```[\w]*\n([\s\S]+?)```/);
                if (match) setEditorValue(match[1]);
              }}>Insert into editor →</button>
            )}
          </div>
        ))}
      </div>
      <div>
        <textarea className="ec-input min-h-[80px]" placeholder="Ask the AI…" value={prompt} onChange={(e) => setPrompt(e.target.value)} />
        <div className="mt-2 flex gap-2">
          <button className="ec-btn-secondary flex-1" disabled={!prompt || send.isPending} onClick={() => send.mutate()}>{send.isPending ? '…' : 'Chat'}</button>
          <button className="ec-btn-primary flex-1" disabled={!prompt || generate.isPending} onClick={() => generate.mutate()}>{generate.isPending ? '…' : 'Generate code'}</button>
        </div>
      </div>
    </div>
  );
}

function CodeReviewPanel({ code, language }: { code: string; language: string }) {
  const [result, setResult] = useState<{ summary: string; findings: any[] } | null>(null);
  const review = useMutation({
    mutationFn: async () => (await api.post('/coding/ai/review', { code, language })).data,
    onSuccess: setResult,
  });
  return (
    <div className="space-y-3">
      <button className="ec-btn-primary w-full" disabled={!code || review.isPending} onClick={() => review.mutate()}>
        <Search size={14} /> {review.isPending ? 'Reviewing…' : 'Run AI code review'}
      </button>
      {result && (
        <div className="space-y-2 text-sm">
          <p className="rounded-lg bg-surface-muted p-3">{result.summary}</p>
          {result.findings.map((f, i) => (
            <div key={i} className={cn('rounded-lg border p-3',
              f.severity === 'high' ? 'border-rose-500/40' : f.severity === 'medium' ? 'border-amber-500/40' : 'border-emerald-500/40')}>
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold uppercase tracking-wider">{f.severity}</span>
                {f.line && <span>line {f.line}</span>}
              </div>
              <p className="mt-1 font-medium">{f.message}</p>
              {f.suggestion && <p className="mt-1 text-xs text-ink-muted">→ {f.suggestion}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TerminalPanel({ projectId }: { projectId: string | null }) {
  const [cmd, setCmd] = useState('');
  const [history, setHistory] = useState<{ cmd: string; out: string; err: string; code: number }[]>([]);
  const run = useMutation({
    mutationFn: async () => (await api.post('/coding/terminal', { command: cmd, timeout_seconds: 30 }, { params: { project_id: projectId } })).data,
    onSuccess: (data) => {
      setHistory([...history, { cmd, out: data.stdout, err: data.stderr, code: data.exit_code }]);
      setCmd('');
    },
  });
  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex-1 overflow-auto rounded-lg bg-zinc-950 p-3 font-mono text-xs text-green-300">
        {history.length === 0 && <p className="text-ink-muted">Type a command below. Sandboxed to the project root. Destructive verbs (rm, del, format…) are blocked.</p>}
        {history.map((h, i) => (
          <div key={i} className="mb-3">
            <p className="text-zinc-500">$ {h.cmd}</p>
            {h.out && <pre className="whitespace-pre-wrap">{h.out}</pre>}
            {h.err && <pre className="whitespace-pre-wrap text-red-400">{h.err}</pre>}
            <p className="text-zinc-600">exit {h.code}</p>
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <input className="ec-input font-mono" placeholder="$ command" value={cmd}
          onKeyDown={(e) => { if (e.key === 'Enter' && cmd && !run.isPending) run.mutate(); }}
          onChange={(e) => setCmd(e.target.value)} />
        <button className="ec-btn-primary" disabled={!cmd || run.isPending || !projectId} onClick={() => run.mutate()}>Run</button>
      </div>
    </div>
  );
}

function GitPanel({ projectId }: { projectId: string | null }) {
  const status = useQuery({
    enabled: !!projectId,
    queryKey: ['coding', 'git', 'status', projectId],
    queryFn: async () => (await api.get('/coding/git/status', { params: { project_id: projectId } })).data,
  });
  const log = useQuery({
    enabled: !!projectId,
    queryKey: ['coding', 'git', 'log', projectId],
    queryFn: async () => (await api.get('/coding/git/log', { params: { project_id: projectId, limit: 20 } })).data,
  });
  const [msg, setMsg] = useState('');
  const commit = useMutation({
    mutationFn: async () => (await api.post('/coding/git/commit', { message: msg, add_all: true }, { params: { project_id: projectId } })).data,
    onSuccess: () => { setMsg(''); status.refetch(); log.refetch(); },
  });
  return (
    <div className="space-y-3 text-sm">
      {status.data ? (
        <div className="rounded-lg bg-surface-muted p-3">
          <p className="flex items-center gap-2"><GitBranch size={14} /> <strong>{status.data.branch}</strong></p>
          <p className="mt-1 text-xs text-ink-muted">{status.data.modified?.length ?? 0} modified · {status.data.staged?.length ?? 0} staged · {status.data.untracked?.length ?? 0} untracked</p>
        </div>
      ) : <p className="text-ink-muted">Not a git repository or not loaded.</p>}
      <div>
        <textarea className="ec-input min-h-[60px]" placeholder="Commit message" value={msg} onChange={(e) => setMsg(e.target.value)} />
        <button className="ec-btn-primary mt-2 w-full" disabled={!msg || commit.isPending} onClick={() => commit.mutate()}>{commit.isPending ? 'Committing…' : 'Commit (add all)'}</button>
      </div>
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">Recent commits</p>
        <ul className="space-y-2">
          {log.data?.commits?.map((c: any) => (
            <li key={c.full_sha} className="rounded border border-border p-2 text-xs">
              <p className="font-mono">{c.sha}</p>
              <p className="mt-1">{c.message}</p>
              <p className="mt-1 text-ink-muted">{c.author}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
