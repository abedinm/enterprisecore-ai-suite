import { useEffect, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Terminal as XTerminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { ChevronRight, History, Loader2, Terminal as TermIcon, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { runCommand } from '../api';

type Props = { projectId: string | null };

type Entry = { cmd: string; cwd: string };

export function TerminalPanel({ projectId }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<XTerminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const bufferRef = useRef<string>('');
  const historyRef = useRef<string[]>([]);
  const histPosRef = useRef<number>(-1);
  const [cwd, setCwd] = useState<string>('');
  const [history, setHistory] = useState<Entry[]>([]);
  const [running, setRunning] = useState(false);
  const runningRef = useRef(false);

  const run = useMutation({
    mutationFn: (cmd: string) => runCommand(projectId!, cmd, 120, cwd || undefined),
  });

  // Initialise xterm exactly once
  useEffect(() => {
    if (!containerRef.current || termRef.current) return;
    const term = new XTerminal({
      cursorBlink: true,
      fontFamily: 'JetBrains Mono, Consolas, monospace',
      fontSize: 12,
      theme: {
        background: '#0c0f16',
        foreground: '#e6edf3',
        cursor: '#a5b4fc',
        selectionBackground: '#4f46e533',
      },
      convertEol: true,
      scrollback: 4000,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(containerRef.current);
    fit.fit();
    termRef.current = term;
    fitRef.current = fit;

    writePrompt(term);

    term.onData(handleData);
    const onResize = () => fitRef.current?.fit();
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      term.dispose();
      termRef.current = null;
    };
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const writePrompt = (term: XTerminal) => {
    const label = cwd ? cwd.split(/[/\\]/).slice(-2).join('/') : '~';
    term.write(`\x1b[34m${label}\x1b[0m \x1b[32m$\x1b[0m `);
  };

  const handleData = async (data: string) => {
    const term = termRef.current!;
    if (runningRef.current) return;
    for (const ch of data) {
      const code = ch.charCodeAt(0);
      if (ch === '\r') {
        const cmd = bufferRef.current.trim();
        term.write('\r\n');
        if (!cmd) {
          writePrompt(term);
          continue;
        }
        bufferRef.current = '';
        historyRef.current = [cmd, ...historyRef.current].slice(0, 100);
        histPosRef.current = -1;
        await execute(cmd);
      } else if (code === 127) {  // backspace
        if (bufferRef.current.length > 0) {
          bufferRef.current = bufferRef.current.slice(0, -1);
          term.write('\b \b');
        }
      } else if (ch === '\x1b[A') {  // up arrow
        if (histPosRef.current + 1 < historyRef.current.length) {
          histPosRef.current += 1;
          const prev = historyRef.current[histPosRef.current];
          while (bufferRef.current.length > 0) {
            term.write('\b \b');
            bufferRef.current = bufferRef.current.slice(0, -1);
          }
          bufferRef.current = prev;
          term.write(prev);
        }
      } else if (ch === '\x1b[B') {  // down arrow
        if (histPosRef.current > 0) {
          histPosRef.current -= 1;
          const next = historyRef.current[histPosRef.current];
          while (bufferRef.current.length > 0) {
            term.write('\b \b');
            bufferRef.current = bufferRef.current.slice(0, -1);
          }
          bufferRef.current = next;
          term.write(next);
        }
      } else if (code === 3) {  // Ctrl+C
        term.write('^C\r\n');
        bufferRef.current = '';
        writePrompt(term);
      } else if (code === 12) {  // Ctrl+L
        term.clear();
        writePrompt(term);
      } else if (code >= 32) {
        bufferRef.current += ch;
        term.write(ch);
      }
    }
  };

  const execute = async (cmd: string) => {
    const term = termRef.current!;
    if (!projectId) {
      term.write('\x1b[33mSelect a project first.\x1b[0m\r\n');
      writePrompt(term);
      return;
    }
    runningRef.current = true;
    setRunning(true);
    setHistory((h) => [...h, { cmd, cwd: cwd || 'project root' }].slice(-100));
    try {
      // built-in `cd` simulation (server only accepts cwd in payload)
      if (cmd.startsWith('cd ') || cmd === 'cd') {
        const target = cmd.replace(/^cd\s*/, '').trim() || '';
        const next = target && target !== '~' ? joinCwd(cwd, target) : '';
        setCwd(next);
        term.write(`\x1b[36mcwd → ${next || '(project root)'}\x1b[0m\r\n`);
        writePrompt(term);
        return;
      }
      if (cmd === 'clear' || cmd === 'cls') {
        term.clear();
        writePrompt(term);
        return;
      }
      const result = await run.mutateAsync(cmd);
      if (result.stdout) term.write(result.stdout.replace(/\r?\n/g, '\r\n'));
      if (!result.stdout.endsWith('\n')) term.write('\r\n');
      if (result.stderr) term.write(`\x1b[31m${result.stderr.replace(/\r?\n/g, '\r\n')}\x1b[0m`);
      term.write(`\x1b[90m[exit ${result.exit_code} • ${result.duration_ms}ms]\x1b[0m\r\n`);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || String(e);
      term.write(`\x1b[31m${msg}\x1b[0m\r\n`);
    } finally {
      runningRef.current = false;
      setRunning(false);
      writePrompt(term);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 items-center gap-2 border-b border-border bg-surface-muted px-3 py-2 text-xs">
        <TermIcon size={12} />
        <span className="font-semibold">Terminal</span>
        <span className="text-ink-subtle">cwd: {cwd || 'project root'}</span>
        {running && <Loader2 size={12} className="animate-spin text-brand-500" />}
        <button className="ml-auto ec-btn-ghost px-2 py-0.5 text-[11px]"
                onClick={() => { termRef.current?.clear(); writePrompt(termRef.current!); }}>
          <Trash2 size={11} /> Clear
        </button>
      </header>
      <div ref={containerRef} className="min-h-0 flex-1 bg-zinc-950" />
      <div className="shrink-0 border-t border-border bg-surface-muted px-3 py-1 text-[10px] text-ink-subtle">
        Sandboxed allowlist: python, node, npm, git, pip, pytest, npm/yarn/pnpm, ruff, eslint, prettier, tsc, cargo, go, dotnet, …
        Use one command per line (no <code>&&</code> / pipes). Use <code>cd folder</code> to change directory.
      </div>
      {history.length > 0 && (
        <details className="shrink-0 border-t border-border bg-surface-muted px-3 py-1 text-[11px]">
          <summary className="cursor-pointer text-ink-muted"><History size={11} className="mr-1 inline" />Session history ({history.length})</summary>
          <ul className="max-h-32 space-y-0.5 overflow-auto pl-4 pt-1 font-mono">
            {history.slice().reverse().map((h, i) => (
              <li key={i} className="truncate"><ChevronRight size={9} className="inline" /> {h.cmd}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function joinCwd(cur: string, frag: string): string {
  if (frag.startsWith('/') || /^[A-Za-z]:/.test(frag)) return frag;
  if (frag === '..') {
    return cur.replace(/[/\\][^/\\]+$/, '');
  }
  return cur ? `${cur.replace(/[/\\]$/, '')}/${frag}` : frag;
}
