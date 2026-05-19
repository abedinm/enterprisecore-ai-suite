import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Plus, Files, Wand2 } from 'lucide-react';
import { api } from '../../lib/api';
import type { Document, DocumentTemplate } from './types';

export function TemplatesTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const templates = useQuery({
    queryKey: ['doc-templates'],
    queryFn: async () => (await api.get<DocumentTemplate[]>('/documents/templates')).data,
  });
  useEffect(() => { if (templates.data?.length && !selectedId) setSelectedId(templates.data[0].id); }, [templates.data, selectedId]);

  const selected = templates.data?.find((t) => t.id === selectedId);
  const variables = useMemo(() => {
    if (!selected) return [];
    const matches = (selected.body || '').match(/\{\{([^}]+)\}\}/g) ?? [];
    return Array.from(new Set(matches.map((m) => m.slice(2, -2).trim())));
  }, [selected]);

  const [varValues, setVarValues] = useState<Record<string, string>>({});
  useEffect(() => { setVarValues({}); }, [selectedId]);
  const [docTitle, setDocTitle] = useState('');

  const instantiate = useMutation({
    mutationFn: async () => (await api.post<Document>(`/documents/templates/${selectedId}/instantiate`, {
      title: docTitle || selected?.name, variables: varValues,
    })).data,
    onSuccess: (d) => { alert(`Document "${d.title}" created.`); qc.invalidateQueries({ queryKey: ['docs'] }); },
  });

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between">
        <div>
          <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><Files size={14} />Templates</p>
          <p className="text-sm text-ink-muted">{templates.data?.length ?? 0} templates · use <code>{'{{name}}'}</code> for variables</p>
        </div>
        <button className="ec-btn-primary" onClick={() => setShow((v) => !v)}><Plus size={14} />{show ? 'Close' : 'New template'}</button>
      </div>

      {show && <TemplateForm onSaved={(t) => { setShow(false); setSelectedId(t.id); qc.invalidateQueries({ queryKey: ['doc-templates'] }); }} />}

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <div className="ec-card p-3">
          <p className="px-2 pb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">Library</p>
          <ul className="space-y-1">
            {templates.data?.length ? templates.data.map((t) => (
              <li key={t.id}>
                <button onClick={() => setSelectedId(t.id)}
                        className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm ${selectedId === t.id ? 'bg-brand-600 text-white' : 'hover:bg-surface-muted'}`}>
                  <span className="font-medium">{t.name}</span>
                  {t.category && <span className={`text-xs ${selectedId === t.id ? 'text-white/70' : 'text-ink-muted'}`}>{t.category}</span>}
                </button>
              </li>
            )) : <li className="px-3 py-6 text-center text-sm text-ink-muted">No templates.</li>}
          </ul>
        </div>

        {selected && (
          <div className="space-y-4">
            <div className="ec-card p-5">
              <h3 className="text-lg font-semibold">{selected.name}</h3>
              {selected.category && <p className="text-xs text-ink-muted">{selected.category}</p>}
              <pre className="mt-3 rounded-lg border border-border bg-surface-muted p-3 text-xs whitespace-pre-wrap">{selected.body}</pre>
            </div>

            <div className="ec-card p-5">
              <p className="mb-3 flex items-center gap-2 text-sm font-semibold"><Wand2 size={14} />Instantiate</p>
              <div className="space-y-3">
                <div><label className="ec-label">New document title</label><input className="ec-input" value={docTitle} onChange={(e) => setDocTitle(e.target.value)} placeholder={selected.name} /></div>
                {variables.length ? (
                  <div className="grid gap-3 md:grid-cols-2">
                    {variables.map((v) => (
                      <div key={v}>
                        <label className="ec-label">{v}</label>
                        <input className="ec-input" value={varValues[v] ?? ''} onChange={(e) => setVarValues((m) => ({ ...m, [v]: e.target.value }))} />
                      </div>
                    ))}
                  </div>
                ) : <p className="text-xs text-ink-muted">No variables detected in template body.</p>}
                <div className="flex justify-end">
                  <button className="ec-btn-primary" disabled={instantiate.isPending} onClick={() => instantiate.mutate()}>
                    {instantiate.isPending ? 'Creating…' : 'Create document'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function TemplateForm({ onSaved }: { onSaved: (t: DocumentTemplate) => void }) {
  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const [body, setBody] = useState('Dear {{customer}},\n\nThank you for {{reason}}.\n\nBest,\n{{sender}}');
  const save = useMutation({
    mutationFn: async () => (await api.post<DocumentTemplate>('/documents/templates', { name, category: category || null, body })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        <div><label className="ec-label">Name</label><input className="ec-input" value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div><label className="ec-label">Category</label><input className="ec-input" value={category} onChange={(e) => setCategory(e.target.value)} /></div>
      </div>
      <div><label className="ec-label">Body</label><textarea rows={8} className="ec-input font-mono text-xs" value={body} onChange={(e) => setBody(e.target.value)} /></div>
      <div className="flex justify-end"><button className="ec-btn-primary" disabled={!name || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save template'}</button></div>
    </div>
  );
}
