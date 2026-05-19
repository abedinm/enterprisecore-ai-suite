import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { FolderTree, Tag } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';
import type { Document, DocumentTag } from './types';

export function OrganizerTab() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<string | null>(null);

  const docs = useQuery({
    queryKey: ['docs'],
    queryFn: async () => (await api.get<Document[]>('/documents')).data,
  });

  const [tagsByDoc, setTagsByDoc] = useState<Record<string, DocumentTag[]>>({});
  useEffect(() => {
    if (!docs.data) return;
    async function load() {
      const results: Record<string, DocumentTag[]> = {};
      for (const d of docs.data!) {
        try {
          results[d.id] = (await api.get<DocumentTag[]>(`/documents/${d.id}/tags`)).data;
        } catch { results[d.id] = []; }
      }
      setTagsByDoc(results);
    }
    load();
  }, [docs.data]);

  const allTags = useMemo(() => {
    const s = new Set<string>();
    Object.values(tagsByDoc).flat().forEach((t) => s.add(t.tag));
    return Array.from(s).sort();
  }, [tagsByDoc]);

  const [newTagFor, setNewTagFor] = useState<string | null>(null);
  const [newTag, setNewTag] = useState('');
  const addTag = useMutation({
    mutationFn: async () => (await api.post<DocumentTag>('/documents/tags', { document_id: newTagFor, tag: newTag })).data,
    onSuccess: (t) => {
      setTagsByDoc((m) => ({ ...m, [t.document_id]: [...(m[t.document_id] ?? []), t] }));
      setNewTagFor(null); setNewTag('');
      qc.invalidateQueries({ queryKey: ['docs'] });
    },
  });

  const filtered = filter
    ? docs.data?.filter((d) => (tagsByDoc[d.id] ?? []).some((t) => t.tag === filter)) ?? []
    : docs.data ?? [];

  return (
    <div className="space-y-5">
      <div>
        <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><FolderTree size={14} />Organizer</p>
        <p className="text-sm text-ink-muted">Tag documents and filter by tag.</p>
      </div>

      <div className="ec-card p-3">
        <p className="px-2 pb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">Tags</p>
        <div className="flex flex-wrap gap-1">
          <button onClick={() => setFilter(null)} className={`rounded-full px-3 py-1 text-xs ${filter === null ? 'bg-brand-600 text-white' : 'bg-surface-muted'}`}>All</button>
          {allTags.length ? allTags.map((t) => (
            <button key={t} onClick={() => setFilter(t)} className={`rounded-full px-3 py-1 text-xs ${filter === t ? 'bg-brand-600 text-white' : 'bg-surface-muted hover:bg-surface-elevated'}`}>
              {t}
            </button>
          )) : <span className="px-3 py-1 text-xs text-ink-muted">No tags yet.</span>}
        </div>
      </div>

      <div className="ec-card overflow-hidden">
        <table className="ec-table">
          <thead><tr><th>Title</th><th>Visibility</th><th>Tags</th><th>Updated</th></tr></thead>
          <tbody>
            {filtered.length ? filtered.map((d) => (
              <tr key={d.id}>
                <td className="font-medium">{d.title}</td>
                <td><span className="ec-badge ec-badge-blue">{d.visibility}</span></td>
                <td className="space-x-1">
                  {(tagsByDoc[d.id] ?? []).map((t) => (
                    <span key={t.id} className="inline-flex items-center gap-1 rounded-full bg-surface-muted px-2 py-0.5 text-xs"><Tag size={10} />{t.tag}</span>
                  ))}
                  {newTagFor === d.id ? (
                    <span className="inline-flex items-center gap-1">
                      <input className="ec-input !py-0.5 !w-24 !text-xs" value={newTag} onChange={(e) => setNewTag(e.target.value)} placeholder="tag" />
                      <button className="ec-btn-primary !py-0.5 !text-xs" disabled={!newTag || addTag.isPending} onClick={() => addTag.mutate()}>Add</button>
                      <button className="ec-btn-ghost !py-0.5 !text-xs" onClick={() => setNewTagFor(null)}>×</button>
                    </span>
                  ) : (
                    <button className="ec-btn-ghost !py-0.5 !text-xs" onClick={() => { setNewTagFor(d.id); setNewTag(''); }}>+ tag</button>
                  )}
                </td>
                <td>{formatDateTime(d.updated_at)}</td>
              </tr>
            )) : <tr><td colSpan={4} className="py-8 text-center text-ink-muted">No documents match.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
