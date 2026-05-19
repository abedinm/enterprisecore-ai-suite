import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Database, KeyRound, Link2, Loader2, Plus, Play, Sparkles, Table2, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { cn } from '../../../lib/utils';
import { MonacoView } from '../EditorTabs';
import {
  aiDbQuery, createDbConnection, dbExecute, dbIntrospect, deleteDbConnection, listDbConnections,
} from '../api';
import type { AiProvider, DBConnection, DBExecuteResult, DBSchema } from '../types';

type Props = { provider: AiProvider; apiKey: string | null; theme: 'vs-dark' | 'vs-light' };

const DIALECTS = ['postgresql', 'mysql', 'sqlite', 'mssql'];

export function DbPanel({ provider, apiKey, theme }: Props) {
  const qc = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [sql, setSql] = useState('');
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiDialect, setAiDialect] = useState('postgresql');
  const [showNew, setShowNew] = useState(false);
  const [result, setResult] = useState<DBExecuteResult | null>(null);

  const conns = useQuery({ queryKey: ['db-connections'], queryFn: () => listDbConnections() });
  const schema = useQuery({
    enabled: !!activeId,
    queryKey: ['db-schema', activeId],
    queryFn: () => dbIntrospect(activeId!),
  });
  const active = useMemo(
    () => (conns.data || []).find((c) => c.id === activeId) || null,
    [conns.data, activeId],
  );

  const execute = useMutation({
    mutationFn: () => dbExecute({ connection_id: activeId!, sql, limit: 500 }),
    onSuccess: setResult,
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Query failed'),
  });

  const ai = useMutation({
    mutationFn: () => aiDbQuery({
      description: aiPrompt,
      dialect: active?.dialect || aiDialect,
      schema_hint: schemaHint(schema.data),
      provider, api_key_override: apiKey,
    }),
    onSuccess: (d) => {
      setSql(d.sql);
      toast.success('SQL generated — review before running');
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Generation failed'),
  });

  const removeConn = useMutation({
    mutationFn: (id: string) => deleteDbConnection(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['db-connections'] }),
  });

  return (
    <div className="grid h-full grid-cols-[220px_1fr] gap-2 p-2">
      <aside className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-border">
        <header className="flex shrink-0 items-center justify-between border-b border-border bg-surface-muted px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
          Connections
          <button title="Add" className="ec-btn-ghost p-0.5" onClick={() => setShowNew((v) => !v)}>
            <Plus size={11} />
          </button>
        </header>
        {showNew && (
          <NewConnectionForm
            onCreated={(c) => { qc.invalidateQueries({ queryKey: ['db-connections'] }); setActiveId(c.id); setShowNew(false); }}
            onCancel={() => setShowNew(false)}
          />
        )}
        <div className="min-h-0 flex-1 overflow-auto p-1">
          {(conns.data || []).map((c) => (
            <div key={c.id} className={cn(
              'group flex items-center gap-1 rounded px-2 py-1 text-xs',
              activeId === c.id ? 'bg-brand-600/15' : 'hover:bg-surface-muted',
            )}>
              <Database size={11} />
              <button onClick={() => { setActiveId(c.id); setResult(null); }} className="flex-1 truncate text-left">{c.name}</button>
              <span className="text-[10px] text-ink-subtle">{c.dialect}</span>
              <button onClick={() => removeConn.mutate(c.id)} className="opacity-0 group-hover:opacity-100 text-rose-500"><Trash2 size={10} /></button>
            </div>
          ))}
          {(conns.data || []).length === 0 && (
            <p className="p-3 text-[11px] text-ink-muted">Add a connection to begin.</p>
          )}
          {active && schema.data && (
            <SchemaBrowser schema={schema.data} onPickTable={(t) => setSql((q) => q ? q : `SELECT * FROM ${t} LIMIT 100;`)} />
          )}
        </div>
      </aside>

      <section className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-border">
        <div className="shrink-0 border-b border-border bg-surface-muted p-2">
          <div className="flex items-center gap-2">
            <Sparkles size={12} className="text-brand-500" />
            <input className="ec-input h-8 flex-1 py-0 text-xs"
                   placeholder="Describe the query in plain English…"
                   value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)} />
            {!active && (
              <select className="ec-input h-8 max-w-[120px] py-0 text-xs" value={aiDialect} onChange={(e) => setAiDialect(e.target.value)}>
                {DIALECTS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            )}
            <button className="ec-btn-secondary text-xs" disabled={!aiPrompt.trim() || ai.isPending}
                    onClick={() => ai.mutate()}>
              {ai.isPending ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
              NL → SQL
            </button>
          </div>
        </div>
        <div className="shrink-0 border-b border-border" style={{ height: 220 }}>
          <MonacoView value={sql} onChange={setSql} language="sql" theme={theme} height="220px" />
        </div>
        <div className="flex shrink-0 items-center gap-2 border-b border-border bg-surface-muted p-2 text-xs">
          <button className="ec-btn-primary" disabled={!active || !sql.trim() || execute.isPending}
                  onClick={() => execute.mutate()}>
            {execute.isPending ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
            Run query
          </button>
          {!active && <span className="text-ink-muted">Select a connection to run</span>}
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          {result ? <ResultTable r={result} /> : (
            <div className="grid h-full place-items-center p-6 text-xs text-ink-muted">
              Run a query to view results. Output is paginated to 500 rows.
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function NewConnectionForm({ onCreated, onCancel }: { onCreated: (c: DBConnection) => void; onCancel: () => void }) {
  const [name, setName] = useState('');
  const [dialect, setDialect] = useState('sqlite');
  const [dsn, setDsn] = useState('');
  const create = useMutation({
    mutationFn: () => createDbConnection({ name, dialect, dsn }),
    onSuccess: onCreated,
    onError: (e: any) => toast.error(e?.response?.data?.detail || 'Failed to add'),
  });
  return (
    <div className="space-y-1 border-b border-border bg-surface-muted p-2 text-xs">
      <input className="ec-input h-7 py-0 text-xs" placeholder="Name" value={name}
             onChange={(e) => setName(e.target.value)} />
      <select className="ec-input h-7 py-0 text-xs" value={dialect}
              onChange={(e) => setDialect(e.target.value)}>
        {DIALECTS.map((d) => <option key={d} value={d}>{d}</option>)}
      </select>
      <input className="ec-input h-7 py-0 font-mono text-[11px]"
             placeholder={dsnPlaceholder(dialect)} value={dsn}
             onChange={(e) => setDsn(e.target.value)} />
      <div className="flex gap-1">
        <button className="ec-btn-primary flex-1 text-[11px]" disabled={!name || !dsn || create.isPending}
                onClick={() => create.mutate()}>
          {create.isPending ? <Loader2 size={10} className="animate-spin" /> : <Link2 size={10} />}
          Connect
        </button>
        <button className="ec-btn-ghost text-[11px]" onClick={onCancel}>×</button>
      </div>
      <p className="text-[10px] text-ink-subtle">DSN is encrypted at rest before being stored.</p>
    </div>
  );
}

function dsnPlaceholder(dialect: string): string {
  switch (dialect) {
    case 'postgresql': return 'postgresql+psycopg2://user:pass@host:5432/db';
    case 'mysql': return 'mysql+pymysql://user:pass@host:3306/db';
    case 'sqlite': return 'sqlite:///path/to/file.db';
    case 'mssql': return 'mssql+pyodbc://user:pass@host/db?driver=ODBC+Driver+17+for+SQL+Server';
    default: return '';
  }
}

function schemaHint(schema: DBSchema | undefined): string | undefined {
  if (!schema) return undefined;
  return schema.tables.slice(0, 30).map((t) => {
    const cols = t.columns.slice(0, 30).map((c) => `${c.name} ${c.type}`).join(', ');
    return `${t.name}(${cols})`;
  }).join('\n');
}

function SchemaBrowser({ schema, onPickTable }: { schema: DBSchema; onPickTable: (t: string) => void }) {
  return (
    <div className="mt-2 border-t border-border pt-2">
      <p className="px-2 text-[10px] uppercase tracking-wider text-ink-muted">Schema · {schema.dialect}</p>
      <ul>
        {schema.tables.map((t) => (
          <li key={t.name} className="text-[11px]">
            <details>
              <summary className="cursor-pointer rounded px-2 py-0.5 hover:bg-surface-muted">
                <Table2 size={10} className="mr-1 inline" />
                <button onClick={(e) => { e.preventDefault(); onPickTable(t.name); }}>{t.name}</button>
              </summary>
              <ul className="ml-4 font-mono text-[10px]">
                {t.columns.map((c) => (
                  <li key={c.name} className="flex items-center gap-1 px-1">
                    {t.primary_key.includes(c.name) && <KeyRound size={9} className="text-amber-500" />}
                    <span>{c.name}</span>
                    <span className="text-ink-subtle">{c.type}</span>
                  </li>
                ))}
              </ul>
            </details>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ResultTable({ r }: { r: DBExecuteResult }) {
  return (
    <div>
      <div className="border-b border-border bg-surface-muted px-3 py-1 text-[11px] text-ink-muted">
        {r.row_count} rows • {r.duration_ms}ms {r.truncated && '(truncated)'}
      </div>
      <div className="overflow-auto">
        <table className="ec-table min-w-full">
          <thead>
            <tr>
              <th className="w-10 text-right text-ink-subtle">#</th>
              {r.columns.map((c) => <th key={c} className="whitespace-nowrap">{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {r.rows.map((row, i) => (
              <tr key={i} className="font-mono text-[11px]">
                <td className="text-right text-ink-subtle">{i + 1}</td>
                {row.map((cell, j) => <td key={j} className="whitespace-pre">{renderCell(cell)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function renderCell(v: unknown): string {
  if (v === null || v === undefined) return '∅';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}
