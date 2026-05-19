import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { History } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';

type Entry = {
  id: string; actor_id: string | null; action: string;
  entity_type: string; entity_id: string | null;
  ip_address: string | null; created_at: string;
};

export function AuditLogTab() {
  const [entityType, setEntityType] = useState('');
  const [action, setAction] = useState('');
  const { data } = useQuery({
    queryKey: ['security', 'audit', entityType, action],
    queryFn: async () => (await api.get<Entry[]>('/security/audit', {
      params: {
        limit: 200,
        ...(entityType ? { entity_type: entityType } : {}),
        ...(action ? { action } : {}),
      },
    })).data,
  });

  const actionColor = (a: string) => {
    if (a === 'create') return 'ec-badge-green';
    if (a === 'delete') return 'ec-badge-rose';
    if (a === 'login' || a === 'logout') return 'ec-badge-blue';
    return 'ec-badge-amber';
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <History className="text-brand-600" size={20} />
        <div>
          <p className="font-semibold">Audit log</p>
          <p className="text-xs text-ink-muted">Every mutation, login, password change, and admin action is recorded.</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <div>
          <label className="ec-label">Entity</label>
          <input className="ec-input !w-48" placeholder="e.g. invoice, user" value={entityType} onChange={(e) => setEntityType(e.target.value)} />
        </div>
        <div>
          <label className="ec-label">Action</label>
          <input className="ec-input !w-48" placeholder="e.g. create, login" value={action} onChange={(e) => setAction(e.target.value)} />
        </div>
      </div>

      <div className="ec-card overflow-x-auto">
        <table className="ec-table">
          <thead><tr><th>When</th><th>Action</th><th>Entity</th><th>Entity ID</th><th>Actor</th><th>IP</th></tr></thead>
          <tbody>
            {data?.length ? data.map((e) => (
              <tr key={e.id}>
                <td className="whitespace-nowrap">{formatDateTime(e.created_at)}</td>
                <td><span className={`ec-badge ${actionColor(e.action)}`}>{e.action}</span></td>
                <td>{e.entity_type}</td>
                <td className="font-mono text-xs text-ink-muted">{e.entity_id ? `${e.entity_id.slice(0, 10)}…` : '—'}</td>
                <td className="font-mono text-xs text-ink-muted">{e.actor_id ? `${e.actor_id.slice(0, 10)}…` : 'system'}</td>
                <td className="font-mono text-xs text-ink-muted">{e.ip_address ?? '—'}</td>
              </tr>
            )) : <tr><td colSpan={6} className="py-8 text-center text-ink-muted">No audit events match.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
