import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import toast from 'react-hot-toast';
import { FileText, RefreshCw, Trash2, Upload } from 'lucide-react';
import { DocStatusBadge } from '../../components/knowledge/DocStatusBadge';
import {
  formatBytes,
  knowledgeApi,
  type DocOut,
  type KbOut,
} from '../../lib/knowledge';
import { formatDateTime, relativeTime } from '../../lib/utils';

type Props = { kb: KbOut };

const ANY_PENDING = new Set(['queued', 'parsing', 'embedding']);

export function KnowledgeDocumentsPanel({ kb }: Props) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<'upload' | 'paste' | 'url'>('upload');
  const [pasteName, setPasteName] = useState('');
  const [pasteText, setPasteText] = useState('');
  const [urlValue, setUrlValue] = useState('');
  const [urlName, setUrlName] = useState('');

  const docsQuery = useQuery({
    queryKey: ['knowledge', 'docs', kb.id],
    queryFn: () => knowledgeApi.listDocs(kb.id),
    refetchInterval: (q) => {
      const data = q.state.data;
      if (!data) return 5_000;
      const anyPending = data.some((d) => ANY_PENDING.has(d.status));
      return anyPending ? 1_500 : 8_000;
    },
  });

  const upload = useMutation({
    mutationFn: async (files: FileList) => {
      const arr = Array.from(files);
      const results: DocOut[] = [];
      for (const file of arr) {
        try {
          const doc = await knowledgeApi.uploadDoc(kb.id, file);
          results.push(doc);
        } catch (e: any) {
          toast.error(`${file.name}: ${e?.response?.data?.detail ?? 'upload failed'}`);
        }
      }
      return results;
    },
    onSuccess: (docs) => {
      if (docs.length > 0) toast.success(`Queued ${docs.length} document${docs.length === 1 ? '' : 's'}`);
      qc.invalidateQueries({ queryKey: ['knowledge', 'docs', kb.id] });
      qc.invalidateQueries({ queryKey: ['knowledge', 'kbs'] });
    },
  });

  const paste = useMutation({
    mutationFn: () => knowledgeApi.pasteDoc(kb.id, pasteName.trim() || 'Pasted note', pasteText),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['knowledge', 'docs', kb.id] });
      qc.invalidateQueries({ queryKey: ['knowledge', 'kbs'] });
      setPasteName('');
      setPasteText('');
      toast.success('Pasted text queued');
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'Paste failed'),
  });

  const submitUrl = useMutation({
    mutationFn: () => knowledgeApi.urlDoc(kb.id, urlValue.trim(), urlName.trim() || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['knowledge', 'docs', kb.id] });
      qc.invalidateQueries({ queryKey: ['knowledge', 'kbs'] });
      setUrlValue('');
      setUrlName('');
      toast.success('URL queued for fetch');
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'Fetch failed'),
  });

  const deleteDoc = useMutation({
    mutationFn: (docId: string) => knowledgeApi.deleteDoc(kb.id, docId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['knowledge', 'docs', kb.id] });
      qc.invalidateQueries({ queryKey: ['knowledge', 'kbs'] });
      toast.success('Document deleted');
    },
  });

  const reindexDoc = useMutation({
    mutationFn: (docId: string) => knowledgeApi.reindexDoc(kb.id, docId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['knowledge', 'docs', kb.id] });
      toast.success('Re-embed queued');
    },
  });

  function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    upload.mutate(files);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    handleFiles(e.dataTransfer.files);
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border bg-surface-muted px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-xs text-ink-subtle">Knowledge base</p>
            <h3 className="text-lg font-semibold">{kb.name}</h3>
            {kb.description && (
              <p className="mt-0.5 text-xs text-ink-muted">{kb.description}</p>
            )}
          </div>
          <div className="text-right text-xs text-ink-muted">
            <p>{kb.document_count} docs · {kb.chunk_count} chunks · {kb.ready_count} ready</p>
            <p className="mt-0.5 text-[11px] text-ink-subtle">
              {kb.embedding_provider}/{kb.embedding_model} · {kb.embedding_dim}d ·
              chunk {kb.chunk_size}/{kb.chunk_overlap}
            </p>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3">
          {(['upload', 'paste', 'url'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-md px-3 py-1 text-xs font-medium ${
                tab === t
                  ? 'bg-brand-600 text-white'
                  : 'bg-surface-elevated text-ink-muted hover:text-ink'
              }`}
            >
              {t === 'upload' ? 'Upload' : t === 'paste' ? 'Paste text' : 'From URL'}
            </button>
          ))}
        </div>

        {tab === 'upload' && (
          <label
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            className="mt-3 flex cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-border bg-surface-elevated px-4 py-6 text-center hover:border-brand-500 hover:bg-brand-50/30 dark:hover:bg-brand-900/10"
          >
            <Upload size={18} className="text-ink-muted" />
            <p className="text-sm">
              <span className="font-medium text-brand-600">Choose files</span> or drag &
              drop
            </p>
            <p className="text-[11px] text-ink-subtle">PDF, DOCX, MD, TXT, HTML — up to 100 MB each</p>
            <input
              type="file"
              className="hidden"
              multiple
              accept=".pdf,.docx,.txt,.md,.markdown,.html,.htm"
              onChange={(e) => {
                handleFiles(e.target.files);
                e.target.value = '';
              }}
            />
          </label>
        )}

        {tab === 'paste' && (
          <div className="mt-3 space-y-2">
            <input
              className="ec-input"
              placeholder="Name (optional, e.g. 'Q1 2026 strategy notes')"
              value={pasteName}
              onChange={(e) => setPasteName(e.target.value)}
            />
            <textarea
              className="ec-input min-h-[120px]"
              placeholder="Paste any text here…"
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
            />
            <button
              className="ec-btn-primary"
              disabled={!pasteText.trim() || paste.isPending}
              onClick={() => paste.mutate()}
            >
              {paste.isPending ? 'Queuing…' : 'Add to KB'}
            </button>
          </div>
        )}

        {tab === 'url' && (
          <div className="mt-3 space-y-2">
            <input
              className="ec-input"
              placeholder="https://example.com/article"
              value={urlValue}
              onChange={(e) => setUrlValue(e.target.value)}
            />
            <input
              className="ec-input"
              placeholder="Name (optional, defaults to URL)"
              value={urlName}
              onChange={(e) => setUrlName(e.target.value)}
            />
            <button
              className="ec-btn-primary"
              disabled={!urlValue.trim() || submitUrl.isPending}
              onClick={() => submitUrl.mutate()}
            >
              {submitUrl.isPending ? 'Fetching…' : 'Fetch & add'}
            </button>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-auto">
        {docsQuery.isLoading && (
          <p className="p-6 text-center text-sm text-ink-muted">Loading documents…</p>
        )}
        {!docsQuery.isLoading && (docsQuery.data?.length ?? 0) === 0 && (
          <div className="grid h-full place-items-center p-8 text-center">
            <div>
              <FileText size={28} className="mx-auto mb-2 text-ink-subtle" />
              <p className="text-sm font-medium">No documents yet</p>
              <p className="mt-1 text-xs text-ink-muted">
                Upload files, paste text or fetch a URL above.
              </p>
            </div>
          </div>
        )}
        {(docsQuery.data?.length ?? 0) > 0 && (
          <table className="ec-table w-full">
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Source</th>
                <th className="text-right">Chunks</th>
                <th className="text-right">Pages</th>
                <th className="text-right">Size</th>
                <th>Added</th>
                <th className="w-20"></th>
              </tr>
            </thead>
            <tbody>
              {docsQuery.data!.map((doc) => (
                <tr key={doc.id} className="group hover:bg-surface-muted/50">
                  <td>
                    <div className="font-medium">{doc.name}</div>
                    {doc.error_message && (
                      <div className="mt-0.5 text-[11px] text-rose-600">
                        {doc.error_message}
                      </div>
                    )}
                  </td>
                  <td>
                    <DocStatusBadge status={doc.status} />
                  </td>
                  <td className="text-xs text-ink-muted">{doc.source_type}</td>
                  <td className="text-right tabular-nums">{doc.chunk_count}</td>
                  <td className="text-right tabular-nums">{doc.page_count || '—'}</td>
                  <td className="text-right tabular-nums text-xs">
                    {formatBytes(doc.byte_size)}
                  </td>
                  <td className="text-xs text-ink-muted" title={formatDateTime(doc.created_at)}>
                    {relativeTime(doc.created_at)}
                  </td>
                  <td>
                    <div className="flex items-center gap-1 opacity-0 transition group-hover:opacity-100">
                      <button
                        className="ec-btn-ghost !p-1.5"
                        title="Re-embed"
                        onClick={() => reindexDoc.mutate(doc.id)}
                      >
                        <RefreshCw size={12} />
                      </button>
                      <button
                        className="ec-btn-ghost !p-1.5 text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-900/20"
                        title="Delete"
                        onClick={() => {
                          if (confirm(`Delete "${doc.name}"?`)) deleteDoc.mutate(doc.id);
                        }}
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
