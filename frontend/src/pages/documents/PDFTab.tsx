import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Download, FileType } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';
import type { Document } from './types';

export function PDFTab() {
  const [search, setSearch] = useState('');
  const docs = useQuery({
    queryKey: ['docs', search],
    queryFn: async () => (await api.get<Document[]>('/documents', { params: search ? { q: search } : {} })).data,
  });

  async function downloadPdf(d: Document) {
    const r = await api.get(`/documents/${d.id}/pdf`, { responseType: 'blob' });
    const url = URL.createObjectURL(r.data as Blob);
    const a = document.createElement('a'); a.href = url; a.download = `${d.title}.pdf`; a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><FileType size={14} />PDF export</p>
          <p className="text-sm text-ink-muted">Export any document as a polished PDF. Two newlines split paragraphs.</p>
        </div>
        <input className="ec-input md:!w-64" placeholder="Search documents…" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <div className="ec-card overflow-hidden">
        <table className="ec-table">
          <thead><tr><th>Title</th><th>Visibility</th><th>Last updated</th><th>Length</th><th></th></tr></thead>
          <tbody>
            {docs.data?.length ? docs.data.map((d) => (
              <tr key={d.id}>
                <td className="font-medium">{d.title}</td>
                <td><span className="ec-badge ec-badge-blue">{d.visibility}</span></td>
                <td>{formatDateTime(d.updated_at)}</td>
                <td>{d.content.length} chars</td>
                <td className="text-right"><button className="ec-btn-primary" onClick={() => downloadPdf(d)}><Download size={14} />PDF</button></td>
              </tr>
            )) : <tr><td colSpan={5} className="py-8 text-center text-ink-muted">No documents.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
