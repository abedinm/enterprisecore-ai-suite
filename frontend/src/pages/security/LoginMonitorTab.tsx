import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, ShieldAlert, XCircle } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';

type Attempt = {
  id: string; email: string; ip_address: string | null;
  success: boolean; reason: string | null; created_at: string;
};
type Summary = {
  total: number; success: number; failure: number;
  top_failing_emails: { email: string; count: number }[];
};

export function LoginMonitorTab() {
  const summary = useQuery({
    queryKey: ['security', 'login-summary'],
    queryFn: async () => (await api.get<Summary>('/security/login-attempts/summary')).data,
  });
  const attempts = useQuery({
    queryKey: ['security', 'login-attempts'],
    queryFn: async () => (await api.get<Attempt[]>('/security/login-attempts', { params: { limit: 200 } })).data,
  });
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3">
        <Tile label="Total attempts" value={summary.data?.total ?? '—'} />
        <Tile label="Successful" value={summary.data?.success ?? '—'} tone="positive" />
        <Tile label="Failed" value={summary.data?.failure ?? '—'} tone="rose" />
      </div>

      {summary.data?.top_failing_emails && summary.data.top_failing_emails.length > 0 && (
        <div className="ec-card p-4">
          <p className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <ShieldAlert size={16} className="text-amber-500" /> Top failing emails
          </p>
          <ul className="space-y-1 text-sm">
            {summary.data.top_failing_emails.map((e) => (
              <li key={e.email} className="flex justify-between">
                <span className="font-mono text-xs">{e.email}</span>
                <strong>{e.count} attempts</strong>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="ec-card overflow-x-auto">
        <table className="ec-table">
          <thead><tr><th>When</th><th>Email</th><th>IP</th><th>Result</th><th>Reason</th></tr></thead>
          <tbody>
            {attempts.data?.length ? attempts.data.map((a) => (
              <tr key={a.id}>
                <td className="whitespace-nowrap">{formatDateTime(a.created_at)}</td>
                <td className="font-mono text-xs">{a.email}</td>
                <td className="font-mono text-xs">{a.ip_address ?? '—'}</td>
                <td>
                  {a.success
                    ? <span className="inline-flex items-center gap-1 text-emerald-500"><CheckCircle2 size={12} /> ok</span>
                    : <span className="inline-flex items-center gap-1 text-rose-500"><XCircle size={12} /> failed</span>}
                </td>
                <td className="text-xs text-ink-muted">{a.reason ?? '—'}</td>
              </tr>
            )) : <tr><td colSpan={5} className="py-8 text-center text-ink-muted">No login attempts logged.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Tile({ label, value, tone }: { label: string; value: any; tone?: 'positive' | 'rose' }) {
  const cls = tone === 'positive' ? 'text-emerald-500' : tone === 'rose' ? 'text-rose-500' : '';
  return (
    <div className="ec-card p-4">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${cls}`}>{value}</p>
    </div>
  );
}
