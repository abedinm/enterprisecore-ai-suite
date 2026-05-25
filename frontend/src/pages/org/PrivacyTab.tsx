import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Download, FileDown, ScrollText, ShieldX } from 'lucide-react';
import { API_BASE } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';
import { gdprApi, type GdprExportJobOut } from '../../lib/gdpr';
import { useAuthStore } from '../../store/auth';
import { PermissionDenied } from './OrgLayout';

export function PrivacyTab() {
  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasRole('Admin'));

  const categoriesQ = useQuery({ queryKey: ['gdpr', 'categories'], queryFn: () => gdprApi.dataCategories() });
  const receiptsQ = useQuery({
    queryKey: ['gdpr', 'receipts'],
    queryFn: () => gdprApi.listReceipts(),
    enabled: isAdmin,
  });

  const [exportJob, setExportJob] = useState<GdprExportJobOut | null>(null);
  const pollRef = useRef<number | null>(null);

  const startExport = useMutation({
    mutationFn: () => gdprApi.requestExport(),
    onSuccess: (job) => {
      setExportJob(job);
      toast.success('Export started');
    },
    onError: () => toast.error('Could not start export'),
  });

  useEffect(() => {
    if (!exportJob || exportJob.status === 'ready' || exportJob.status === 'failed') return;
    pollRef.current = window.setInterval(async () => {
      try {
        const updated = await gdprApi.getExport(exportJob.id);
        setExportJob(updated);
        if (updated.status === 'ready' || updated.status === 'failed') {
          if (pollRef.current !== null) window.clearInterval(pollRef.current);
        }
      } catch {
        /* keep polling */
      }
    }, 2000);
    return () => {
      if (pollRef.current !== null) window.clearInterval(pollRef.current);
    };
  }, [exportJob?.id, exportJob?.status]);

  // Erasure form (admin)
  const [eraseUserId, setEraseUserId] = useState('');
  const [eraseReason, setEraseReason] = useState('');
  const erasure = useMutation({
    mutationFn: () => gdprApi.erasureRequest(eraseUserId.trim(), eraseReason.trim()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['gdpr', 'receipts'] });
      setEraseUserId('');
      setEraseReason('');
      toast.success('Erasure complete');
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Erasure failed'),
  });

  const downloadHref = exportJob?.download_url
    ? (exportJob.download_url.startsWith('/')
        ? API_BASE.replace(/\/api\/v1\/?$/, '') + exportJob.download_url
        : exportJob.download_url)
    : null;

  return (
    <div className="space-y-4">
      <div className="ec-card p-5 space-y-4">
        <header>
          <h2 className="text-lg font-semibold flex items-center gap-2"><FileDown size={18} /> Export my data</h2>
          <p className="text-sm text-ink-muted">Download a full JSON archive of your personal records.</p>
        </header>
        <div className="flex items-center gap-3">
          <button
            className="ec-btn-primary"
            onClick={() => startExport.mutate()}
            disabled={startExport.isPending || (exportJob !== null && exportJob.status !== 'ready' && exportJob.status !== 'failed')}
            data-testid="gdpr-export"
          >
            {startExport.isPending ? 'Starting…' : 'Request export'}
          </button>
          {exportJob ? (
            <div className="text-sm">
              Status: <span className="ec-badge-green">{exportJob.status}</span>
              {exportJob.record_count ? <span className="ml-2 text-ink-muted">{exportJob.record_count} records</span> : null}
            </div>
          ) : null}
          {downloadHref ? (
            <a className="ec-btn-secondary" href={downloadHref} target="_blank" rel="noreferrer">
              <Download size={16} /> Download
            </a>
          ) : null}
        </div>
      </div>

      {isAdmin ? (
        <div className="ec-card p-5 space-y-4">
          <header>
            <h2 className="text-lg font-semibold flex items-center gap-2"><ShieldX size={18} /> Erase a user</h2>
            <p className="text-sm text-ink-muted">Anonymizes the user&apos;s personal data while preserving audit trails.</p>
          </header>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="ec-label" htmlFor="erase-uid">User ID</label>
              <input
                id="erase-uid"
                className="ec-input font-mono text-xs"
                value={eraseUserId}
                onChange={(e) => setEraseUserId(e.target.value)}
                data-testid="erase-user-id"
              />
            </div>
            <div>
              <label className="ec-label" htmlFor="erase-reason">Reason</label>
              <input
                id="erase-reason"
                className="ec-input"
                value={eraseReason}
                onChange={(e) => setEraseReason(e.target.value)}
              />
            </div>
          </div>
          <button
            className="ec-btn-primary"
            onClick={() => erasure.mutate()}
            disabled={erasure.isPending || !eraseUserId}
            data-testid="erase-submit"
          >
            {erasure.isPending ? 'Erasing…' : 'Erase user'}
          </button>

          <div>
            <h3 className="text-sm font-semibold">Erasure receipts</h3>
            {receiptsQ.isLoading ? (
              <p className="mt-2 text-sm text-ink-muted">Loading…</p>
            ) : (receiptsQ.data?.length ?? 0) === 0 ? (
              <p className="mt-2 text-sm text-ink-muted">No erasure receipts yet.</p>
            ) : (
              <table className="mt-2 w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-ink-subtle">
                    <th className="py-2 pr-3">When</th>
                    <th className="py-2 pr-3">User (anonymized)</th>
                    <th className="py-2 pr-3">Reason</th>
                    <th className="py-2 pr-3">Records</th>
                  </tr>
                </thead>
                <tbody>
                  {receiptsQ.data!.map((r) => (
                    <tr key={r.id} className="border-b border-border/40">
                      <td className="py-2 pr-3 text-ink-muted">{formatDateTime(r.completed_at)}</td>
                      <td className="py-2 pr-3 font-mono text-xs">{r.user_email_anonymized}</td>
                      <td className="py-2 pr-3 text-ink-muted">{r.reason || '—'}</td>
                      <td className="py-2 pr-3 text-ink-muted">{r.records_anonymized}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      ) : (
        <PermissionDenied what="erase users" />
      )}

      <div className="ec-card p-5 space-y-3">
        <header>
          <h2 className="text-lg font-semibold flex items-center gap-2"><ScrollText size={18} /> Data we store</h2>
          <p className="text-sm text-ink-muted">Categories of personal data EnterpriseCore keeps for each user.</p>
        </header>
        {categoriesQ.isLoading ? (
          <p className="text-sm text-ink-muted">Loading…</p>
        ) : (
          <ul className="space-y-3">
            {categoriesQ.data?.map((c) => (
              <li key={c.name} className="rounded-lg border border-border bg-surface-muted/30 p-3">
                <p className="font-semibold">{c.name}</p>
                <p className="text-sm text-ink-muted">{c.description}</p>
                <p className="mt-1 text-xs text-ink-subtle">
                  Examples: {c.examples.join(', ')}. Retention: {c.retention}.
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
