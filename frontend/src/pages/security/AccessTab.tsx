import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Users } from 'lucide-react';
import { api } from '../../lib/api';

type AccessRow = { id: string; email: string; full_name: string; role: string; is_active: boolean };
const ROLES = ['Admin', 'Manager', 'Developer', 'Employee'];

export function AccessTab() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ['security', 'access'],
    queryFn: async () => (await api.get<AccessRow[]>('/security/access')).data,
  });
  const grant = useMutation({
    mutationFn: async ({ user_id, role }: { user_id: string; role: string }) =>
      (await api.post('/security/access/grant', { user_id, role })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['security', 'access'] }),
  });
  const disable = useMutation({
    mutationFn: async (id: string) => (await api.post(`/security/access/${id}/disable`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['security', 'access'] }),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Users className="text-brand-600" size={20} />
        <div>
          <p className="font-semibold">Access control</p>
          <p className="text-xs text-ink-muted">Roles: Admin {'>'} Manager {'>'} Developer {'>'} Employee. Disabled users cannot sign in.</p>
        </div>
      </div>

      <div className="ec-card overflow-x-auto">
        <table className="ec-table">
          <thead><tr><th>Email</th><th>Name</th><th>Role</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {data?.length ? data.map((u) => (
              <tr key={u.id} className={!u.is_active ? 'opacity-60' : ''}>
                <td className="font-mono text-xs">{u.email}</td>
                <td>{u.full_name}</td>
                <td>
                  <select className="ec-input !py-1 !w-32" value={u.role}
                          onChange={(e) => grant.mutate({ user_id: u.id, role: e.target.value })}>
                    {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
                <td>
                  {u.is_active
                    ? <span className="ec-badge ec-badge-green">active</span>
                    : <span className="ec-badge ec-badge-rose">disabled</span>}
                </td>
                <td className="text-right">
                  {u.is_active && (
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Disable ' + u.email + '?')) disable.mutate(u.id); }}>
                      Disable
                    </button>
                  )}
                </td>
              </tr>
            )) : <tr><td colSpan={5} className="py-8 text-center text-ink-muted">Loading…</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
