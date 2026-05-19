import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { FileSignature, ShieldCheck } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';
import type { Document, ESignature } from './types';

export function ESignTab() {
  const qc = useQueryClient();
  const [docId, setDocId] = useState('');
  const [signerName, setSignerName] = useState('');
  const [signerEmail, setSignerEmail] = useState('');

  const docs = useQuery({
    queryKey: ['docs'],
    queryFn: async () => (await api.get<Document[]>('/documents')).data,
  });
  useEffect(() => { if (docs.data?.length && !docId) setDocId(docs.data[0].id); }, [docs.data, docId]);

  const signatures = useQuery({
    enabled: !!docId,
    queryKey: ['docs', docId, 'signatures'],
    queryFn: async () => (await api.get<ESignature[]>(`/documents/${docId}/signatures`)).data,
  });

  const sign = useMutation({
    mutationFn: async () => (await api.post<ESignature>('/documents/signatures', {
      document_id: docId, signer_name: signerName, signer_email: signerEmail || null,
    })).data,
    onSuccess: () => { setSignerName(''); setSignerEmail(''); qc.invalidateQueries({ queryKey: ['docs', docId, 'signatures'] }); },
  });

  return (
    <div className="space-y-5">
      <div>
        <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><FileSignature size={14} />E-Signature</p>
        <p className="text-sm text-ink-muted">Each signature is hashed with the document content, signer name &amp; date — tamper-evident.</p>
      </div>

      <div className="ec-card p-5 space-y-3">
        <p className="text-sm font-semibold">Sign a document</p>
        <div className="grid gap-3 md:grid-cols-4">
          <div className="md:col-span-2"><label className="ec-label">Document</label>
            <select className="ec-input" value={docId} onChange={(e) => setDocId(e.target.value)}>
              <option value="">—</option>
              {docs.data?.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
            </select>
          </div>
          <div><label className="ec-label">Signer name</label><input className="ec-input" value={signerName} onChange={(e) => setSignerName(e.target.value)} /></div>
          <div><label className="ec-label">Signer email</label><input className="ec-input" value={signerEmail} onChange={(e) => setSignerEmail(e.target.value)} /></div>
        </div>
        <div className="flex justify-end">
          <button className="ec-btn-primary" disabled={!docId || !signerName || sign.isPending} onClick={() => sign.mutate()}>
            <FileSignature size={14} />{sign.isPending ? 'Signing…' : 'Sign document'}
          </button>
        </div>
      </div>

      <div className="ec-card overflow-hidden">
        <div className="border-b border-border bg-surface-muted p-3 text-sm font-semibold">Signatures on selected document</div>
        <table className="ec-table">
          <thead><tr><th>Signer</th><th>Email</th><th>Verified</th><th>Hash</th></tr></thead>
          <tbody>
            {signatures.data?.length ? signatures.data.map((s) => (
              <tr key={s.id}>
                <td className="font-medium">{s.signer_name}</td>
                <td>{s.signer_email ?? '—'}</td>
                <td>{s.is_verified ? <ShieldCheck size={16} className="text-emerald-500" /> : 'No'}</td>
                <td className="font-mono text-[10px] text-ink-muted truncate max-w-xs" title={s.signature_hash}>{s.signature_hash}</td>
              </tr>
            )) : <tr><td colSpan={4} className="py-6 text-center text-ink-muted">No signatures yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
