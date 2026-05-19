import { useEffect, useRef, useState } from 'react';
import Editor, { DiffEditor, type OnMount } from '@monaco-editor/react';
import type * as monacoEditor from 'monaco-editor';
import { CircleDot, FileCode, X } from 'lucide-react';
import { cn } from '../../lib/utils';
import type { EditorTab } from './types';

const MONACO_KNOWN_LANGS = new Set([
  'plaintext','python','javascript','typescript','tsx','jsx','json','jsonc','html','css','scss','less','sass',
  'markdown','yaml','xml','toml','ini','dockerfile','shell','powershell','bat','sql','java','kotlin','scala',
  'csharp','fsharp','go','rust','ruby','php','perl','lua','r','dart','swift','cpp','c','objective-c','vb',
  'graphql','protobuf','hcl','elixir','erlang','haskell','clojure','elm','julia','asm','sol','vue','svelte',
]);

function monacoLang(lang: string | null): string {
  if (!lang) return 'plaintext';
  if (MONACO_KNOWN_LANGS.has(lang)) return lang;
  if (lang === 'restructuredtext') return 'plaintext';
  if (lang === 'mdx') return 'markdown';
  if (lang === 'thrift' || lang === 'crystal') return 'plaintext';
  if (lang === 'astro') return 'html';
  return lang;
}

type Props = {
  tabs: EditorTab[];
  activePath: string | null;
  onSelect: (path: string) => void;
  onClose: (path: string) => void;
  onChange: (path: string, value: string) => void;
  theme: 'vs-dark' | 'vs-light';
  onSelectionChange?: (path: string, selected: string) => void;
};

export function EditorTabs({
  tabs, activePath, onSelect, onClose, onChange, theme, onSelectionChange,
}: Props) {
  const active = tabs.find((t) => t.path === activePath);
  const editorRef = useRef<monacoEditor.editor.IStandaloneCodeEditor | null>(null);

  const handleMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      window.dispatchEvent(new CustomEvent('ec:editor:save-shortcut'));
    });
    editor.onDidChangeCursorSelection(() => {
      if (!onSelectionChange || !activePath) return;
      const sel = editor.getModel()?.getValueInRange(editor.getSelection()!);
      onSelectionChange(activePath, sel || '');
    });
  };

  useEffect(() => {
    editorRef.current?.focus();
  }, [activePath]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 overflow-x-auto border-b border-border bg-surface-muted">
        {tabs.map((t) => (
          <button
            key={t.path}
            onClick={() => onSelect(t.path)}
            className={cn(
              'group flex items-center gap-2 border-r border-border px-3 py-1.5 text-xs',
              t.path === activePath ? 'bg-surface-elevated text-ink' : 'text-ink-muted hover:bg-surface-elevated',
            )}
          >
            <FileCode size={11} className="opacity-70" />
            <span className="max-w-[160px] truncate">{baseName(t.path)}</span>
            {t.dirty && <CircleDot size={9} className="text-amber-500" />}
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => { e.stopPropagation(); onClose(t.path); }}
              className="ml-1 rounded p-0.5 opacity-60 hover:bg-surface-muted hover:opacity-100"
            >
              <X size={11} />
            </span>
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1">
        {active ? (
          <Editor
            key={active.path}
            theme={theme}
            language={monacoLang(active.language)}
            value={active.current}
            onChange={(v) => onChange(active.path, v ?? '')}
            onMount={handleMount}
            options={{
              minimap: { enabled: true, scale: 0.6 },
              fontSize: 13,
              fontLigatures: true,
              fontFamily: "JetBrains Mono, Consolas, monospace",
              wordWrap: 'on',
              tabSize: 2,
              renderWhitespace: 'selection',
              automaticLayout: true,
              scrollBeyondLastLine: false,
              smoothScrolling: true,
              cursorBlinking: 'smooth',
              padding: { top: 12, bottom: 24 },
              bracketPairColorization: { enabled: true },
              suggest: { preview: true },
              quickSuggestions: { other: true, comments: false, strings: true },
            }}
          />
        ) : (
          <EmptyEditor />
        )}
      </div>
    </div>
  );
}

function EmptyEditor() {
  return (
    <div className="grid h-full place-items-center bg-surface-muted text-center text-sm text-ink-muted">
      <div className="max-w-md space-y-2 p-6">
        <p className="text-lg font-medium text-ink">No file open</p>
        <p>Open a file from the explorer to start editing — Ctrl/⌘+S to save.</p>
        <p className="text-xs">The editor supports 60+ languages, IntelliSense, multi-cursor, bracket colorization, and a diff view for git changes.</p>
      </div>
    </div>
  );
}

export function DiffViewer({
  original, modified, language, theme,
}: {
  original: string; modified: string; language: string; theme: 'vs-dark' | 'vs-light';
}) {
  return (
    <DiffEditor
      original={original}
      modified={modified}
      language={monacoLang(language)}
      theme={theme}
      options={{
        renderSideBySide: true,
        readOnly: true,
        minimap: { enabled: false },
        fontSize: 12,
        fontFamily: 'JetBrains Mono, Consolas, monospace',
        scrollBeyondLastLine: false,
        automaticLayout: true,
      }}
    />
  );
}

export function MonacoView({
  value, language, theme, onChange, readOnly = false, height = '300px',
}: {
  value: string; language: string; theme: 'vs-dark' | 'vs-light';
  onChange?: (v: string) => void; readOnly?: boolean; height?: string;
}) {
  return (
    <Editor
      height={height}
      theme={theme}
      language={monacoLang(language)}
      value={value}
      onChange={(v) => onChange?.(v ?? '')}
      options={{
        readOnly,
        minimap: { enabled: false },
        fontSize: 12,
        wordWrap: 'on',
        scrollBeyondLastLine: false,
        automaticLayout: true,
        padding: { top: 8, bottom: 8 },
        fontFamily: 'JetBrains Mono, Consolas, monospace',
      }}
    />
  );
}

function baseName(p: string): string {
  const m = p.match(/[^/\\]+$/);
  return m ? m[0] : p;
}
