import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Replace, Check } from 'lucide-react';
import { api } from '../../lib/api';
import type { Document } from './types';

type BulkRenameOut = { renamed: number; new_titles: Record<string, string> };

export function BulkRenameTab() {
  const docs = useQuery({
    queryKey: ['docs'],
    queryFn: async () => (await api.get<Document[]>('/documents')).data,
  });

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [prefix, setPrefix] = useState('');
  const [suffix, setSuffix] = useState('');
  const [findStr, setFindStr] = useState('');
  const [replStr, setReplStr] = useState('');
  const [result, setResult] = useState<BulkRenameOut | null>(null);

  function toggle(id: string) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }
  function toggleAll() {
    if (!docs.data) return;
    setSelected(selected.size === docs.data.length ? new Set() : new Set(docs.data.map((d) => d.id)));
  }

  function previewName(orig: string): string {
    let n = orig;
    if (findStr) n = n.split(findStr).join(replStr);
    if (prefix) n = prefix + n;
    if (suffix) n = n + suffix;
    return n;
  }

  const apply = useMutation({
    mutationFn: async () => (await api.post<BulkRenameOut>('/documents/bulk-rename', {
      document_ids: Array.from(selected),
      prefix: prefix || null,
      suffix: suffix || null,
      replace: findStr ? { [findStr]: replStr } : null,
    })).data,
    onSuccess: (d) => { setResult(d); setSelected(new Set()); },
  });

  return (
    <div className="space-y-5">
      <div>
        <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><Replace size={14} />Bulk rename</p>
        <p className="text-sm text-ink-muted">Apply prefix, suffix, and find/replace to selected documents at once.</p>
      </div>

      <div className="ec-card p-4 grid gap-3 md:grid-cols-4">
        <div><label className="ec-label">Prefix</label><input className="ec-input" value={prefix} onChange={(e) => setPrefix(e.target.value)} placeholder="[2026] " /></div>
        <div><label className="ec-label">Suffix</label><input className="ec-input" value={suffix} onChange={(e) => setSuffix(e.target.value)} placeholder=" - DRAFT" /></div>
        <div><label className="ec-label">Find</label><input className="ec-input" value={findStr} onChange={(e) => setFindStr(e.target.value)} placeholder="old text" /></div>
        <div><label className="ec-label">Replace with</label><input className="ec-input" value={replStr} onChange={(e) => setReplStr(e.target.value)} placeholder="new text" /></div>
      </div>

      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-muted">{selected.size} of {docs.data?.length ?? 0} selected</p>
        <div className="flex gap-2">
          <button className="ec-btn-secondary" onClick={toggleAll}>{selected.size === docs.data?.length ? 'Deselect all' : 'Select all'}</button>
          <button className="ec-btn-primary" disabled={!selected.size || apply.isPending} onClick={() => apply.mutate()}>
            <Check size={14} />{apply.isPending ? 'Renaming…' : `Apply to ${selected.size}`}
          </button>
        </div>
      </div>

      {result && (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/5 px-4 py-2 text-sm">
          ✓ Renamed <strong>{result.renamed}</strong> documents.
        </div>
      )}

      <div className="ec-card overflow-hidden">
        <table className="ec-table">
          <thead><tr><th></th><th>Current title</th><th>Preview</th></tr></thead>
          <tbody>
            {docs.data?.length ? docs.data.map((d) => {
              const preview = previewName(d.title);
              const changed = preview !== d.title;
              return (
                <tr key={d.id} className={selected.has(d.id) ? 'bg-brand-600/5' : ''}>
                  <td><input type="checkbox" checked={selected.has(d.id)} onChange={() => toggle(d.id)} /></td>
                  <td>{d.title}</td>
                  <td className={changed ? 'font-medium text-brand-600' : 'text-ink-muted'}>{preview}</td>
                </tr>
              );
            }) : <tr><td colSpan={3} className="py-8 text-center text-ink-muted">No documents.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
