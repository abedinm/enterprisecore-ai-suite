import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Share2, Plus, Trash2 } from 'lucide-react';
import { api } from '../../lib/api';
import type { Document, DocumentShare } from './types';

const PERMISSIONS = ['read', 'comment', 'edit'];

export function SharingTab() {
  const qc = useQueryClient();
  const [docId, setDocId] = useState('');
  const [userId, setUserId] = useState('');
  const [permission, setPermission] = useState('read');

  const docs = useQuery({
    queryKey: ['docs'],
    queryFn: async () => (await api.get<Document[]>('/documents')).data,
  });
  useEffect(() => { if (docs.data?.length && !docId) setDocId(docs.data[0].id); }, [docs.data, docId]);

  const shares = useQuery({
    enabled: !!docId,
    queryKey: ['docs', docId, 'shares'],
    queryFn: async () => (await api.get<DocumentShare[]>(`/documents/${docId}/shares`)).data,
  });

  const add = useMutation({
    mutationFn: async () => (await api.post<DocumentShare>('/documents/shares', {
      document_id: docId, user_id: userId || null, permission,
    })).data,
    onSuccess: () => { setUserId(''); qc.invalidateQueries({ queryKey: ['docs', docId, 'shares'] }); },
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/documents/shares/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['docs', docId, 'shares'] }),
  });

  return (
    <div className="space-y-5">
      <div>
        <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><Share2 size={14} />Sharing</p>
        <p className="text-sm text-ink-muted">Grant per-user read / comment / edit permissions on documents.</p>
      </div>

      <div className="ec-card p-5 space-y-3">
        <div>
          <label className="ec-label">Document</label>
          <select className="ec-input" value={docId} onChange={(e) => setDocId(e.target.value)}>
            <option value="">—</option>
            {docs.data?.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
          </select>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <div><label className="ec-label">User ID (or leave blank for public link)</label><input className="ec-input" value={userId} onChange={(e) => setUserId(e.target.value)} placeholder="user id or empty" /></div>
          <div><label className="ec-label">Permission</label>
            <select className="ec-input" value={permission} onChange={(e) => setPermission(e.target.value)}>
              {PERMISSIONS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div className="flex items-end"><button className="ec-btn-primary w-full" disabled={!docId || add.isPending} onClick={() => add.mutate()}><Plus size={14} />Grant</button></div>
        </div>
      </div>

      <div className="ec-card overflow-hidden">
        <table className="ec-table">
          <thead><tr><th>User</th><th>Permission</th><th></th></tr></thead>
          <tbody>
            {shares.data?.length ? shares.data.map((s) => (
              <tr key={s.id}>
                <td className="font-mono text-xs">{s.user_id ?? '(public link)'}</td>
                <td><span className={`ec-badge ${s.permission === 'edit' ? 'ec-badge-amber' : s.permission === 'comment' ? 'ec-badge-blue' : 'ec-badge'}`}>{s.permission}</span></td>
                <td className="text-right">
                  <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Revoke share?')) remove.mutate(s.id); }}><Trash2 size={14} /></button>
                </td>
              </tr>
            )) : <tr><td colSpan={3} className="py-6 text-center text-ink-muted">No shares.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
