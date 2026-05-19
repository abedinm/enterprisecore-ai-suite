import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { History, RotateCcw } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';
import type { Document, DocumentVersion } from './types';

export function VersionsTab() {
  const qc = useQueryClient();
  const [docId, setDocId] = useState<string>('');
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);

  const docs = useQuery({
    queryKey: ['docs'],
    queryFn: async () => (await api.get<Document[]>('/documents')).data,
  });
  useEffect(() => { if (docs.data?.length && !docId) setDocId(docs.data[0].id); }, [docs.data, docId]);

  const versions = useQuery({
    enabled: !!docId,
    queryKey: ['docs', docId, 'versions'],
    queryFn: async () => (await api.get<DocumentVersion[]>(`/documents/${docId}/versions`)).data,
  });

  const restore = useMutation({
    mutationFn: async (v: number) => (await api.post(`/documents/${docId}/versions/${v}/restore`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['docs'] });
      qc.invalidateQueries({ queryKey: ['docs', docId, 'versions'] });
      alert('Version restored as current document content.');
    },
  });

  const currentDoc = docs.data?.find((d) => d.id === docId);
  const selected = versions.data?.find((v) => v.version_number === selectedVersion) ?? versions.data?.[0] ?? null;
  useEffect(() => { setSelectedVersion(null); }, [docId]);

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><History size={14} />Version history</p>
          <p className="text-sm text-ink-muted">Every save snapshots the previous content automatically.</p>
        </div>
        <div>
          <label className="ec-label">Document</label>
          <select className="ec-input md:!w-72" value={docId} onChange={(e) => setDocId(e.target.value)}>
            <option value="">—</option>
            {docs.data?.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
          </select>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <div className="ec-card p-3">
          <p className="px-2 pb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">Versions ({versions.data?.length ?? 0})</p>
          <ul className="space-y-1">
            {versions.data?.length ? versions.data.map((v) => (
              <li key={v.id}>
                <button onClick={() => setSelectedVersion(v.version_number)}
                  className={`block w-full rounded-md px-3 py-2 text-left text-sm ${selected?.version_number === v.version_number ? 'bg-brand-600 text-white' : 'hover:bg-surface-muted'}`}>
                  <p className="font-medium">v{v.version_number}</p>
                  <p className={`text-xs ${selected?.version_number === v.version_number ? 'text-white/70' : 'text-ink-muted'}`}>{formatDateTime(v.created_at)}</p>
                </button>
              </li>
            )) : <li className="px-3 py-6 text-center text-sm text-ink-muted">No history yet.</li>}
          </ul>
        </div>

        {selected && (
          <div className="space-y-3">
            <div className="ec-card p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-lg font-semibold">{currentDoc?.title} — v{selected.version_number}</h3>
                  <p className="text-xs text-ink-muted">{formatDateTime(selected.created_at)}</p>
                </div>
                <button className="ec-btn-primary" onClick={() => { if (confirm(`Restore v${selected.version_number} as current?`)) restore.mutate(selected.version_number); }}>
                  <RotateCcw size={14} />Restore this version
                </button>
              </div>
              <pre className="mt-3 max-h-[60vh] overflow-y-auto rounded-lg border border-border bg-surface-muted p-4 text-xs whitespace-pre-wrap font-mono">{selected.content}</pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
