import { FormEvent, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Copy, Send, UserPlus, X } from 'lucide-react';
import { api, type User, type UserRole } from '../../lib/api';
import { tenantApi } from '../../lib/tenant';
import { useAuthStore } from '../../store/auth';
import { formatDateTime } from '../../lib/format';
import { PermissionDenied } from './OrgLayout';

const ROLE_OPTIONS: UserRole[] = ['Admin', 'Manager', 'Employee', 'Developer', 'Student', 'Teacher', 'Registrar', 'Dean'];

export function UsersTab() {
  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasRole('Admin'));
  const usersQ = useQuery({
    queryKey: ['users', 'list'],
    queryFn: () => api.get<User[]>('/users').then((r) => r.data),
  });

  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<UserRole>('Employee');
  const [lastInviteToken, setLastInviteToken] = useState<string | null>(null);

  const invite = useMutation({
    mutationFn: () => tenantApi.invite({ email: inviteEmail.trim().toLowerCase(), role: inviteRole }),
    onSuccess: (data) => {
      setLastInviteToken(data.token ?? null);
      toast.success('Invite created');
      setInviteEmail('');
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Could not send invite'),
  });

  function copyToken() {
    if (!lastInviteToken) return;
    const url = `${window.location.origin}/#/auth/accept-invite?token=${lastInviteToken}`;
    navigator.clipboard.writeText(url).then(() => toast.success('Invite link copied'));
  }

  const rows = useMemo(() => usersQ.data ?? [], [usersQ.data]);

  return (
    <div className="space-y-4">
      <div className="ec-card p-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Users</h2>
            <p className="text-sm text-ink-muted">Members of your organization.</p>
          </div>
          {isAdmin ? (
            <button
              className="ec-btn-primary"
              onClick={() => {
                setInviteOpen(true);
                setLastInviteToken(null);
              }}
              data-testid="invite-open"
            >
              <UserPlus size={16} /> Invite user
            </button>
          ) : null}
        </div>

        <div className="mt-4 overflow-x-auto">
          {usersQ.isLoading ? (
            <p className="py-6 text-center text-sm text-ink-muted">Loading users…</p>
          ) : rows.length === 0 ? (
            <p className="py-6 text-center text-sm text-ink-muted">No users yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-ink-subtle">
                  <th className="py-2 pr-3">Name</th>
                  <th className="py-2 pr-3">Email</th>
                  <th className="py-2 pr-3">Role</th>
                  <th className="py-2 pr-3">Last active</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((u) => (
                  <tr key={u.id} className="border-b border-border/40">
                    <td className="py-2 pr-3">{u.full_name}</td>
                    <td className="py-2 pr-3 text-ink-muted">{u.email}</td>
                    <td className="py-2 pr-3"><span className="ec-badge-green">{u.role}</span></td>
                    <td className="py-2 pr-3 text-ink-muted">
                      {u.last_login_at ? formatDateTime(u.last_login_at) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {!isAdmin ? <div className="mt-4"><PermissionDenied what="invite or manage users" /></div> : null}
      </div>

      {inviteOpen ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-ink/40 backdrop-blur-sm p-4">
          <div className="ec-card w-full max-w-md p-5 relative">
            <button
              className="absolute right-2 top-2 rounded-md p-1.5 text-ink-muted hover:bg-surface-muted"
              onClick={() => setInviteOpen(false)}
              aria-label="Close"
            >
              <X size={16} />
            </button>
            <h3 className="text-lg font-semibold">Invite a user</h3>
            <p className="mt-1 text-sm text-ink-muted">They&apos;ll receive a magic link to set up their account.</p>

            {!lastInviteToken ? (
              <form
                className="mt-4 space-y-3"
                onSubmit={(e: FormEvent) => {
                  e.preventDefault();
                  invite.mutate();
                }}
              >
                <div>
                  <label className="ec-label" htmlFor="inv-email">Email</label>
                  <input
                    id="inv-email"
                    className="ec-input"
                    type="email"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    required
                    data-testid="invite-email-input"
                  />
                </div>
                <div>
                  <label className="ec-label" htmlFor="inv-role">Role</label>
                  <select
                    id="inv-role"
                    className="ec-input"
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value as UserRole)}
                    data-testid="invite-role"
                  >
                    {ROLE_OPTIONS.map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                </div>
                <button className="ec-btn-primary w-full" type="submit" disabled={invite.isPending} data-testid="invite-send">
                  <Send size={16} /> {invite.isPending ? 'Sending…' : 'Send invite'}
                </button>
              </form>
            ) : (
              <div className="mt-4 space-y-3">
                <p className="text-sm text-ink-muted">Invite created. Copy this link and share it with the user — it expires in 7 days.</p>
                <div className="ec-card bg-surface-muted/60 p-3 text-xs font-mono break-all">
                  {`${window.location.origin}/#/auth/accept-invite?token=${lastInviteToken}`}
                </div>
                <div className="flex gap-2">
                  <button className="ec-btn-secondary flex-1" onClick={copyToken}>
                    <Copy size={16} /> Copy link
                  </button>
                  <button className="ec-btn-primary flex-1" onClick={() => setInviteOpen(false)}>Done</button>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
