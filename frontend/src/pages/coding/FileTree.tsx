import { useCallback, useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, File, FilePlus, FolderClosed, FolderOpen, FolderPlus, Pencil, Trash2 } from 'lucide-react';
import { cn } from '../../lib/utils';
import type { FileNode } from './types';

type Props = {
  node: FileNode;
  rootPath: string;
  activePath: string | null;
  onOpen: (path: string) => void;
  onCreate: (parentPath: string, kind: 'file' | 'dir') => void;
  onRename: (path: string) => void;
  onDelete: (path: string) => void;
};

function joinSep(node: FileNode, root: string) {
  // The backend already returns absolute paths for each node.
  return node.path.replace(root, '').replace(/^[/\\]/, '') || node.name;
}

export function FileTree(props: Props) {
  return <Branch depth={0} {...props} />;
}

function Branch({
  node, rootPath, activePath, onOpen, onCreate, onRename, onDelete, depth,
}: Props & { depth: number }) {
  const [open, setOpen] = useState(depth < 1);
  const children = node.children ?? [];
  const display = depth === 0 ? node.name : joinSep(node, rootPath).split(/[/\\]/).pop() || node.name;

  if (!node.is_dir) {
    return (
      <FileRow
        node={node}
        depth={depth}
        active={activePath === node.path}
        onOpen={() => onOpen(node.path)}
        onRename={() => onRename(node.path)}
        onDelete={() => onDelete(node.path)}
        display={display}
      />
    );
  }

  return (
    <div>
      <div
        className="group flex items-center gap-1 rounded px-1 py-0.5 hover:bg-surface-muted"
        style={{ paddingLeft: depth * 12 + 4 }}
      >
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex flex-1 items-center gap-1 text-left text-sm"
        >
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          {open ? <FolderOpen size={13} className="text-amber-500" /> : <FolderClosed size={13} className="text-amber-500" />}
          <span className="truncate">{display}</span>
        </button>
        <div className="opacity-0 group-hover:opacity-100 flex items-center gap-0.5">
          <button title="New file" onClick={(e) => { e.stopPropagation(); onCreate(node.path, 'file'); }}
                  className="rounded p-0.5 hover:bg-surface-elevated"><FilePlus size={11} /></button>
          <button title="New folder" onClick={(e) => { e.stopPropagation(); onCreate(node.path, 'dir'); }}
                  className="rounded p-0.5 hover:bg-surface-elevated"><FolderPlus size={11} /></button>
          {depth > 0 && (
            <>
              <button title="Rename" onClick={(e) => { e.stopPropagation(); onRename(node.path); }}
                      className="rounded p-0.5 hover:bg-surface-elevated"><Pencil size={11} /></button>
              <button title="Delete" onClick={(e) => { e.stopPropagation(); onDelete(node.path); }}
                      className="rounded p-0.5 text-rose-500 hover:bg-surface-elevated"><Trash2 size={11} /></button>
            </>
          )}
        </div>
      </div>
      {open && (
        <div>
          {children.map((c) => (
            <Branch key={c.path}
                    node={c} rootPath={rootPath} activePath={activePath}
                    onOpen={onOpen} onCreate={onCreate}
                    onRename={onRename} onDelete={onDelete}
                    depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function FileRow({
  node, depth, active, onOpen, onRename, onDelete, display,
}: {
  node: FileNode; depth: number; active: boolean;
  onOpen: () => void; onRename: () => void; onDelete: () => void; display: string;
}) {
  return (
    <div className={cn(
      'group flex items-center gap-1 rounded px-1 py-0.5',
      active ? 'bg-brand-600/15' : 'hover:bg-surface-muted',
    )}
      style={{ paddingLeft: depth * 12 + 18 }}
    >
      <button onClick={onOpen} className="flex flex-1 items-center gap-1 text-left text-sm">
        <File size={12} className="text-ink-subtle" />
        <span className={cn('truncate', active && 'font-medium text-brand-600')}>{display}</span>
      </button>
      <div className="opacity-0 group-hover:opacity-100 flex items-center gap-0.5">
        <button title="Rename" onClick={(e) => { e.stopPropagation(); onRename(); }}
                className="rounded p-0.5 hover:bg-surface-elevated"><Pencil size={11} /></button>
        <button title="Delete" onClick={(e) => { e.stopPropagation(); onDelete(); }}
                className="rounded p-0.5 text-rose-500 hover:bg-surface-elevated"><Trash2 size={11} /></button>
      </div>
    </div>
  );
}

/** Flatten the tree to a list of file paths (no directories). Useful for
 *  context-file pickers, search jumps, etc. */
export function flattenFiles(node: FileNode | null): string[] {
  if (!node) return [];
  const out: string[] = [];
  const walk = (n: FileNode) => {
    if (!n.is_dir) out.push(n.path);
    n.children?.forEach(walk);
  };
  walk(node);
  return out;
}

export function useFileSearch(node: FileNode | null) {
  const all = useMemo(() => flattenFiles(node), [node]);
  const search = useCallback((q: string, limit = 40) => {
    if (!q) return all.slice(0, limit);
    const lower = q.toLowerCase();
    return all.filter((p) => p.toLowerCase().includes(lower)).slice(0, limit);
  }, [all]);
  return { all, search };
}
