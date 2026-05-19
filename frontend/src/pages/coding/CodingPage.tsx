import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Boxes, Code2, Database, FolderOpen, FolderPlus, GitBranch, Globe, Hammer,
  Library, Loader2, Plus, RefreshCw, Regex as RegexIcon, Save, Search, Settings as SettingsIcon,
  Sparkles, Terminal as TermIcon, Trash2, X,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { cn } from '../../lib/utils';
import { EditorTabs } from './EditorTabs';
import { FileTree, useFileSearch } from './FileTree';
import { DEFAULT_MODEL, PROVIDER_LABELS } from './providers';
import { useApiKeys } from './useApiKeys';
import { ChatPanel } from './panels/ChatPanel';
import { CodeToolsPanel } from './panels/CodeToolsPanel';
import { TerminalPanel } from './panels/TerminalPanel';
import { GitPanel } from './panels/GitPanel';
import { MultiFilePanel } from './panels/MultiFilePanel';
import { SnippetsPanel } from './panels/SnippetsPanel';
import { ApiTesterPanel } from './panels/ApiTesterPanel';
import { DbPanel } from './panels/DbPanel';
import { RegexPanel } from './panels/RegexPanel';
import { ApiKeySettingsPanel } from './panels/SettingsPanel';
import {
  createProject, deleteFile, deleteProject, fileTree, listProjects,
  newFile, readFile, renameFile, searchInFiles, writeFile,
} from './api';
import { useThemeStore } from '../../store/theme';
import type { AiProvider, EditorTab, FileNode } from './types';

type RightPanel =
  | 'chat' | 'code-tools' | 'multi-file' | 'terminal' | 'git'
  | 'snippets' | 'api' | 'db' | 'regex' | 'settings';

const RIGHT_PANELS: { id: RightPanel; label: string; icon: any }[] = [
  { id: 'chat', label: 'AI Chat', icon: Sparkles },
  { id: 'code-tools', label: 'AI Tools', icon: Hammer },
  { id: 'multi-file', label: 'Multi-file', icon: Boxes },
  { id: 'terminal', label: 'Terminal', icon: TermIcon },
  { id: 'git', label: 'Git', icon: GitBranch },
  { id: 'snippets', label: 'Snippets', icon: Library },
  { id: 'api', label: 'API Tester', icon: Globe },
  { id: 'db', label: 'DB Query', icon: Database },
  { id: 'regex', label: 'Regex', icon: RegexIcon },
  { id: 'settings', label: 'Keys', icon: SettingsIcon },
];

export function CodingPage() {
  const qc = useQueryClient();
  const resolved = useThemeStore((s) => s.resolved);
  const monacoTheme: 'vs-dark' | 'vs-light' =
    resolved === 'light' ? 'vs-light' : 'vs-dark';

  const [projectId, setProjectId] = useState<string | null>(null);
  const [tabs, setTabs] = useState<EditorTab[]>([]);
  const [activePath, setActivePath] = useState<string | null>(null);
  const [selection, setSelection] = useState('');
  const [rightPanel, setRightPanel] = useState<RightPanel>('chat');
  const [showNewProject, setShowNewProject] = useState(false);
  const [searchVisible, setSearchVisible] = useState(false);

  const { keys, status } = useApiKeys();
  const [provider, setProvider] = useState<AiProvider>('anthropic');
  const [model, setModel] = useState(DEFAULT_MODEL.anthropic);
  const apiKey = keys[provider];

  useEffect(() => {
    // When provider changes, snap to its default model
    setModel(DEFAULT_MODEL[provider]);
  }, [provider]);

  // ---- Queries ---------------------------------------------------------
  const projects = useQuery({ queryKey: ['coding', 'projects'], queryFn: listProjects });
  useEffect(() => {
    if (!projectId && projects.data?.length) setProjectId(projects.data[0].id);
  }, [projects.data, projectId]);

  const treeQ = useQuery({
    enabled: !!projectId,
    queryKey: ['coding', 'tree', projectId],
    queryFn: () => fileTree(projectId!, 4),
  });

  // ---- Tabs ------------------------------------------------------------
  const openFile = useCallback(async (path: string) => {
    if (!projectId) return;
    const existing = tabs.find((t) => t.path === path);
    if (existing) {
      setActivePath(path);
      return;
    }
    try {
      const f = await readFile(projectId, path);
      const tab: EditorTab = {
        path: f.path,
        language: f.language || 'plaintext',
        original: f.content,
        current: f.content,
        dirty: false,
      };
      setTabs((t) => [...t, tab]);
      setActivePath(f.path);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Failed to open file');
    }
  }, [tabs, projectId]);

  const closeTab = useCallback((path: string) => {
    setTabs((t) => {
      const idx = t.findIndex((x) => x.path === path);
      if (idx < 0) return t;
      const tgt = t[idx];
      if (tgt.dirty && !confirm(`Discard unsaved changes in ${path}?`)) return t;
      const next = t.filter((x) => x.path !== path);
      if (path === activePath) setActivePath(next[Math.max(0, idx - 1)]?.path || null);
      return next;
    });
  }, [activePath]);

  const updateActive = useCallback((newContent: string) => {
    if (!activePath) return;
    setTabs((t) => t.map((x) => x.path === activePath
      ? { ...x, current: newContent, dirty: newContent !== x.original }
      : x));
  }, [activePath]);

  const setTabValue = useCallback((path: string, value: string) => {
    setTabs((t) => t.map((x) => x.path === path
      ? { ...x, current: value, dirty: value !== x.original }
      : x));
  }, []);

  const onSelection = useCallback((_path: string, sel: string) => {
    setSelection(sel);
  }, []);

  // ---- Save ------------------------------------------------------------
  const save = useMutation({
    mutationFn: async () => {
      if (!projectId || !activePath) return;
      const tab = tabs.find((t) => t.path === activePath);
      if (!tab) return;
      await writeFile(projectId, tab.path, tab.current);
      return tab.path;
    },
    onSuccess: (path) => {
      if (path) {
        setTabs((t) => t.map((x) => x.path === path ? { ...x, original: x.current, dirty: false } : x));
        toast.success(`Saved ${baseName(path)}`);
      }
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Save failed'),
  });

  // Save on Ctrl/⌘+S anywhere in the page
  useEffect(() => {
    const onSave = () => save.mutate();
    window.addEventListener('ec:editor:save-shortcut', onSave);
    return () => window.removeEventListener('ec:editor:save-shortcut', onSave);
  }, [save]);

  // ---- File tree mutations --------------------------------------------
  const refreshTree = () => qc.invalidateQueries({ queryKey: ['coding', 'tree', projectId] });

  const create = useMutation({
    mutationFn: ({ parent, kind }: { parent: string; kind: 'file' | 'dir' }) => {
      const name = prompt(`Name of new ${kind}:`);
      if (!name) return Promise.resolve(null);
      const path = parent.replace(/[/\\]$/, '') + '/' + name;
      return newFile(projectId!, path, kind === 'dir');
    },
    onSuccess: () => refreshTree(),
  });

  const rename = useMutation({
    mutationFn: (oldPath: string) => {
      const next = prompt('Rename to:', oldPath);
      if (!next || next === oldPath) return Promise.resolve(null);
      return renameFile(projectId!, oldPath, next);
    },
    onSuccess: () => refreshTree(),
  });

  const removeFile = useMutation({
    mutationFn: (p: string) => {
      if (!confirm(`Delete ${p}?`)) return Promise.resolve(null);
      return deleteFile(projectId!, p);
    },
    onSuccess: () => refreshTree(),
  });

  const removeProject = useMutation({
    mutationFn: (id: string) => deleteProject(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['coding', 'projects'] });
      setProjectId(null);
      setTabs([]);
    },
  });

  // ---- Code insertion --------------------------------------------------
  const insertAtCursor = useCallback((code: string) => {
    if (!activePath) {
      toast.error('Open a file before inserting code.');
      return;
    }
    setTabs((t) => t.map((x) => x.path === activePath
      ? { ...x, current: x.current + (x.current.endsWith('\n') ? '' : '\n') + code, dirty: true }
      : x));
  }, [activePath]);

  const replaceFileContent = useCallback((newContent: string) => {
    if (!activePath) return;
    setTabs((t) => t.map((x) => x.path === activePath
      ? { ...x, current: newContent, dirty: newContent !== x.original }
      : x));
  }, [activePath]);

  // ---- Electron menu + global keyboard integration --------------------
  useEffect(() => {
    const off1 = window.enterpriseCore?.on('menu:save-file', () => save.mutate());
    const off2 = window.enterpriseCore?.on('menu:new-file', async () => {
      if (!projectId) return;
      const p = prompt('New file name (relative to project root):');
      if (p) {
        await newFile(projectId, p);
        refreshTree();
      }
    });
    const off3 = window.enterpriseCore?.on('menu:open-project', async () => {
      const dir = await window.enterpriseCore?.dialog.openDirectory();
      if (dir) {
        const name = dir.split(/[/\\]/).pop() || 'New project';
        const p = await createProject({ name, path: dir });
        qc.invalidateQueries({ queryKey: ['coding', 'projects'] });
        setProjectId(p.id);
      }
    });
    const off4 = window.enterpriseCore?.on('menu:command-palette', () => setSearchVisible(true));
    return () => { off1?.(); off2?.(); off3?.(); off4?.(); };
  }, [projectId, save, qc]);  // eslint-disable-line

  // Global keyboard shortcuts wired at the document level so they fire
  // even when the focus is in Monaco / xterm / a chat textarea.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      if (!mod) return;
      // Ctrl/⌘+P — Quick Open (files). Shift+P bumps to in-content search.
      if (e.key.toLowerCase() === 'p' && !e.altKey) {
        e.preventDefault();
        setSearchVisible(true);
        return;
      }
      // Ctrl/⌘+B — toggle right rail panels (sequential navigation)
      if (e.key.toLowerCase() === 'b' && !e.shiftKey) {
        e.preventDefault();
        setRightPanel((p) => {
          const idx = RIGHT_PANELS.findIndex((x) => x.id === p);
          return RIGHT_PANELS[(idx + 1) % RIGHT_PANELS.length].id;
        });
        return;
      }
      // Ctrl/⌘+W — close active tab
      if (e.key.toLowerCase() === 'w' && activePath) {
        e.preventDefault();
        closeTab(activePath);
        return;
      }
      // Ctrl/⌘+1..9 — jump to right-rail tab by index
      const digit = Number(e.key);
      if (digit >= 1 && digit <= 9 && RIGHT_PANELS[digit - 1]) {
        e.preventDefault();
        setRightPanel(RIGHT_PANELS[digit - 1].id);
        return;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [activePath, closeTab]);

  const activeTab = useMemo(() => tabs.find((t) => t.path === activePath) ?? null, [tabs, activePath]);
  const tree = treeQ.data ?? null;
  const { all: allPaths } = useFileSearch(tree);

  return (
    <div className="relative flex h-[calc(100vh-9rem)] gap-3">
      <Sidebar
        projects={projects.data || []}
        loading={projects.isLoading}
        projectId={projectId}
        onSelect={(id) => { setProjectId(id); setTabs([]); setActivePath(null); }}
        onNew={() => setShowNewProject(true)}
        onDelete={(id) => removeProject.mutate(id)}
        tree={tree}
        treeRoot={tree?.path || ''}
        onRefresh={refreshTree}
        onOpenFile={openFile}
        onNewItem={(parent, kind) => create.mutate({ parent, kind })}
        onRenameFile={(p) => rename.mutate(p)}
        onDeleteFile={(p) => removeFile.mutate(p)}
        onToggleSearch={() => setSearchVisible((v) => !v)}
      />

      {showNewProject && (
        <NewProjectModal
          onClose={() => setShowNewProject(false)}
          onCreated={(p) => {
            qc.invalidateQueries({ queryKey: ['coding', 'projects'] });
            setProjectId(p.id);
            setShowNewProject(false);
          }}
        />
      )}

      {searchVisible && projectId && (
        <SearchModal projectId={projectId} files={allPaths}
                     onPick={(p) => { openFile(p); setSearchVisible(false); }}
                     onClose={() => setSearchVisible(false)} />
      )}

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-surface-elevated">
        <Toolbar
          activeTab={activeTab}
          onSave={() => save.mutate()}
          saving={save.isPending}
          onSearch={() => setSearchVisible(true)}
        />
        <div className="min-h-0 flex-1">
          <EditorTabs
            tabs={tabs}
            activePath={activePath}
            onSelect={setActivePath}
            onClose={closeTab}
            onChange={setTabValue}
            theme={monacoTheme}
            onSelectionChange={onSelection}
          />
        </div>
      </main>

      <section className="flex w-[440px] shrink-0 flex-col overflow-hidden rounded-xl border border-border bg-surface-elevated">
        <nav className="flex shrink-0 overflow-x-auto border-b border-border bg-surface-muted">
          {RIGHT_PANELS.map((p) => {
            const Icon = p.icon;
            return (
              <button
                key={p.id}
                onClick={() => setRightPanel(p.id)}
                className={cn(
                  'flex items-center gap-1 whitespace-nowrap border-r border-border px-2.5 py-2 text-[11px] last:border-r-0',
                  rightPanel === p.id
                    ? 'bg-surface-elevated font-semibold text-brand-600'
                    : 'text-ink-muted hover:bg-surface-elevated',
                )}
              >
                <Icon size={11} /> {p.label}
              </button>
            );
          })}
        </nav>
        <div className="relative min-h-0 flex-1">
          {rightPanel === 'chat' && (
            <ChatPanel
              projectId={projectId} tabs={tabs} activePath={activePath}
              provider={provider} model={model} apiKey={apiKey}
              onProviderChange={setProvider} onModelChange={setModel}
              onInsert={insertAtCursor}
            />
          )}
          {rightPanel === 'code-tools' && (
            <CodeToolsPanel
              activeTab={activeTab} selection={selection}
              provider={provider} model={model} apiKey={apiKey}
              theme={monacoTheme} onApply={replaceFileContent}
              onInsert={insertAtCursor} projectId={projectId}
              contextFiles={activePath ? [activePath] : []}
            />
          )}
          {rightPanel === 'multi-file' && (
            <MultiFilePanel
              projectId={projectId} tree={tree}
              provider={provider} apiKey={apiKey} theme={monacoTheme}
              onRefreshTree={refreshTree}
            />
          )}
          {rightPanel === 'terminal' && <TerminalPanel projectId={projectId} />}
          {rightPanel === 'git' && <GitPanel projectId={projectId} theme={monacoTheme} />}
          {rightPanel === 'snippets' && (
            <SnippetsPanel onInsert={insertAtCursor} theme={monacoTheme}
                           provider={provider} apiKey={apiKey} />
          )}
          {rightPanel === 'api' && <ApiTesterPanel theme={monacoTheme} />}
          {rightPanel === 'db' && <DbPanel provider={provider} apiKey={apiKey} theme={monacoTheme} />}
          {rightPanel === 'regex' && <RegexPanel provider={provider} apiKey={apiKey} />}
          {rightPanel === 'settings' && <ApiKeySettingsPanel />}
        </div>
        <ProviderStatusBar provider={provider} apiKey={apiKey} status={status} />
      </section>
    </div>
  );
}

// ---- Sidebar ------------------------------------------------------------
function Sidebar({
  projects, loading, projectId, onSelect, onNew, onDelete,
  tree, treeRoot, onRefresh, onOpenFile, onNewItem, onRenameFile, onDeleteFile,
  onToggleSearch,
}: {
  projects: { id: string; name: string; path: string; is_git: boolean }[];
  loading: boolean;
  projectId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  tree: FileNode | null;
  treeRoot: string;
  onRefresh: () => void;
  onOpenFile: (p: string) => void;
  onNewItem: (parent: string, kind: 'file' | 'dir') => void;
  onRenameFile: (p: string) => void;
  onDeleteFile: (p: string) => void;
  onToggleSearch: () => void;
}) {
  return (
    <aside className="flex w-72 shrink-0 flex-col overflow-hidden rounded-xl border border-border bg-surface-elevated">
      <header className="flex shrink-0 items-center justify-between border-b border-border bg-surface-muted px-3 py-2">
        <p className="flex items-center gap-2 text-sm font-semibold"><Code2 size={14} /> Projects</p>
        <div className="flex items-center gap-1">
          <button className="ec-btn-ghost p-1" title="Search in files" onClick={onToggleSearch}><Search size={12} /></button>
          <button className="ec-btn-ghost p-1" title="Refresh" onClick={onRefresh}><RefreshCw size={12} /></button>
          <button className="ec-btn-ghost p-1" title="New project" onClick={onNew}><FolderPlus size={13} /></button>
        </div>
      </header>
      <ul className="shrink-0 max-h-44 space-y-0.5 overflow-auto border-b border-border p-2">
        {loading && <li className="text-xs text-ink-muted">Loading…</li>}
        {projects.map((p) => (
          <li key={p.id} className={cn(
            'group flex items-center gap-2 rounded px-2 py-1 text-xs',
            projectId === p.id ? 'bg-brand-600/15 text-brand-600 font-medium' : 'hover:bg-surface-muted',
          )}>
            <FolderOpen size={11} />
            <button onClick={() => onSelect(p.id)} className="flex-1 truncate text-left">{p.name}</button>
            {p.is_git && <GitBranch size={10} className="opacity-60" />}
            <button onClick={() => onDelete(p.id)} className="opacity-0 group-hover:opacity-100 text-rose-500"><Trash2 size={10} /></button>
          </li>
        ))}
        {!loading && projects.length === 0 && (
          <li className="text-xs text-ink-muted">No projects yet. Click + to add one.</li>
        )}
      </ul>
      <div className="min-h-0 flex-1 overflow-auto py-1">
        {projectId && tree ? (
          <FileTree
            node={tree}
            rootPath={treeRoot}
            activePath={null}
            onOpen={onOpenFile}
            onCreate={onNewItem}
            onRename={onRenameFile}
            onDelete={onDeleteFile}
          />
        ) : (
          <p className="p-3 text-xs text-ink-muted">Select a project to browse files.</p>
        )}
      </div>
    </aside>
  );
}

// ---- Toolbar ------------------------------------------------------------
function Toolbar({ activeTab, onSave, saving, onSearch }: {
  activeTab: EditorTab | null;
  onSave: () => void;
  saving: boolean;
  onSearch: () => void;
}) {
  return (
    <div className="flex shrink-0 items-center gap-2 border-b border-border bg-surface-muted px-3 py-2 text-xs">
      <Code2 size={12} className="text-ink-muted" />
      <span className="font-mono">{activeTab?.path || 'No file open'}</span>
      {activeTab?.language && (
        <span className="ec-badge bg-surface-elevated text-ink-muted">{activeTab.language}</span>
      )}
      {activeTab?.dirty && <span className="text-amber-400">●</span>}
      <button className="ml-auto ec-btn-ghost px-2 py-0.5" onClick={onSearch}>
        <Search size={11} /> Quick open
        <kbd className="ml-1 rounded border border-border px-1 text-[10px]">Ctrl/⌘ P</kbd>
      </button>
      <span className="text-[10px] text-ink-subtle" title="Tab through right-rail panels">
        <kbd className="rounded border border-border px-1">Ctrl/⌘ B</kbd>
      </span>
      <button className="ec-btn-primary" disabled={!activeTab || saving} onClick={onSave}>
        {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
        Save
      </button>
    </div>
  );
}

// ---- Provider status bar ------------------------------------------------
function ProviderStatusBar({ provider, apiKey, status }: {
  provider: AiProvider; apiKey: string | null;
  status: { encrypted: boolean; isDesktop: boolean };
}) {
  return (
    <footer className="flex shrink-0 items-center justify-between border-t border-border bg-surface-muted px-3 py-1 text-[10px] text-ink-muted">
      <span>{PROVIDER_LABELS[provider]} • {apiKey ? 'BYO key' : 'server key'}</span>
      <span>{status.isDesktop ? (status.encrypted ? 'OS-encrypted vault' : 'local vault') : 'web localStorage'}</span>
    </footer>
  );
}

// ---- New project modal --------------------------------------------------
function NewProjectModal({ onClose, onCreated }: {
  onClose: () => void; onCreated: (p: { id: string; name: string }) => void;
}) {
  const [name, setName] = useState('');
  const [path, setPath] = useState('');
  const [description, setDescription] = useState('');
  const [language, setLanguage] = useState('');

  const create = useMutation({
    mutationFn: () => createProject({
      name, path, description: description || undefined,
      language_primary: language || undefined,
    }),
    onSuccess: onCreated,
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Failed to create project'),
  });

  const pickFolder = async () => {
    const dir = await window.enterpriseCore?.dialog.openDirectory();
    if (dir) {
      setPath(dir);
      if (!name) setName(dir.split(/[/\\]/).pop() || 'New project');
    }
  };

  return (
    <div className="absolute inset-0 z-40 flex items-start justify-center bg-black/50 p-12" onClick={onClose}>
      <div className="w-full max-w-md rounded-lg border border-border bg-surface-elevated p-4 shadow-xl"
           onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <p className="text-sm font-semibold">Add code project</p>
          <button onClick={onClose}><X size={14} /></button>
        </div>
        <label className="ec-label">Project name</label>
        <input className="ec-input" placeholder="e.g. acme-api" value={name} onChange={(e) => setName(e.target.value)} />
        <label className="ec-label mt-2">Absolute path on disk</label>
        <div className="flex gap-2">
          <input className="ec-input flex-1 font-mono text-xs" placeholder="F:/code/acme-api"
                 value={path} onChange={(e) => setPath(e.target.value)} />
          {window.enterpriseCore && (
            <button className="ec-btn-secondary" onClick={pickFolder}>Browse…</button>
          )}
        </div>
        <label className="ec-label mt-2">Primary language (optional)</label>
        <input className="ec-input" placeholder="python, typescript, …" value={language}
               onChange={(e) => setLanguage(e.target.value)} />
        <label className="ec-label mt-2">Description (optional)</label>
        <textarea className="ec-input min-h-[60px]" value={description} onChange={(e) => setDescription(e.target.value)} />
        <div className="mt-3 flex justify-end gap-2">
          <button className="ec-btn-ghost text-xs" onClick={onClose}>Cancel</button>
          <button className="ec-btn-primary" disabled={!name || !path || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
            Create
          </button>
        </div>
      </div>
    </div>
  );
}

// ---- Quick open / search modal ------------------------------------------
function SearchModal({
  projectId, files, onPick, onClose,
}: { projectId: string; files: string[]; onPick: (p: string) => void; onClose: () => void }) {
  const [q, setQ] = useState('');
  const [mode, setMode] = useState<'files' | 'content'>('files');
  const matches = useMemo(() => {
    if (mode !== 'files') return [];
    const lower = q.toLowerCase();
    return files.filter((p) => p.toLowerCase().includes(lower)).slice(0, 40);
  }, [files, q, mode]);

  const content = useQuery({
    enabled: mode === 'content' && q.length >= 2,
    queryKey: ['search-in-files', projectId, q],
    queryFn: () => searchInFiles(projectId, q),
  });

  return (
    <div className="absolute inset-0 z-40 flex items-start justify-center bg-black/50 p-12" onClick={onClose}>
      <div className="w-full max-w-2xl rounded-lg border border-border bg-surface-elevated p-3 shadow-xl"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-border pb-2">
          <Search size={12} />
          <input autoFocus className="ec-input border-0 bg-transparent text-sm" placeholder="Type to search…"
                 value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="flex rounded-md border border-border bg-surface-muted">
            <button onClick={() => setMode('files')}
                    className={cn('px-2 py-1 text-[11px]', mode === 'files' && 'bg-surface-elevated font-semibold text-brand-600')}>
              Files
            </button>
            <button onClick={() => setMode('content')}
                    className={cn('px-2 py-1 text-[11px]', mode === 'content' && 'bg-surface-elevated font-semibold text-brand-600')}>
              In content
            </button>
          </div>
          <button onClick={onClose}><X size={14} /></button>
        </div>
        <ul className="mt-2 max-h-96 space-y-0.5 overflow-auto">
          {mode === 'files' && matches.map((p) => (
            <li key={p}>
              <button onClick={() => onPick(p)} className="w-full rounded px-2 py-1 text-left font-mono text-xs hover:bg-surface-muted">
                {p}
              </button>
            </li>
          ))}
          {mode === 'content' && content.data?.hits.map((h, i) => (
            <li key={i}>
              <button onClick={() => onPick(h.path)} className="block w-full rounded px-2 py-1 text-left hover:bg-surface-muted">
                <p className="font-mono text-xs">{h.path}<span className="ml-2 text-ink-subtle">:{h.line}</span></p>
                <p className="truncate text-[11px] text-ink-muted">{h.snippet}</p>
              </button>
            </li>
          ))}
          {mode === 'content' && content.isFetching && <li className="p-3 text-xs"><Loader2 size={12} className="animate-spin" /></li>}
          {mode === 'files' && matches.length === 0 && q && (
            <li className="p-3 text-xs text-ink-muted">No file matches.</li>
          )}
        </ul>
      </div>
    </div>
  );
}

function baseName(p: string): string {
  return p.split(/[/\\]/).pop() || p;
}
