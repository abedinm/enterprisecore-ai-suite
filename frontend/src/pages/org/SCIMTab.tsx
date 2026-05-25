import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Copy, KeyRound, Plus, Trash2, X } from 'lucide-react';
import { scimBaseUrl, ssoApi } from '../../lib/sso';
import { useAuthStore } from '../../store/auth';
import { formatDate, formatDateTime } from '../../lib/utils';
import { PermissionDenied } from './OrgLayout';

export function SCIMTab() {
  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasRole('Admin'));
  const tokensQ = useQuery({
    queryKey: ['sso', 'scim', 'tokens'],
    queryFn: () => ssoApi.listScimTokens(),
    enabled: isAdmin,
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState('');
  const [ttlDays, setTtlDays] = useState(365);
  const [createdToken, setCreatedToken] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => ssoApi.createScimToken({ name, ttl_days: ttlDays }),
    onSuccess: (data) => {
      setCreatedToken(data.token);
      setName('');
      qc.invalidateQueries({ queryKey: ['sso', 'scim', 'tokens'] });
    },
    onError: () => toast.error('Could not create token'),
  });

  const revoke = useMutation({
    mutationFn: (id: string) => ssoApi.revokeScimToken(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sso', 'scim', 'tokens'] });
      toast.success('Token revoked');
    },
  });

  if (!isAdmin) return <PermissionDenied what="manage SCIM tokens" />;

  return (
    <div className="space-y-4">
      <div className="ec-card p-5 space-y-4">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2"><KeyRound size={18} /> SCIM</h2>
            <p className="text-sm text-ink-muted">Bearer tokens for your IdP&apos;s SCIM provisioning.</p>
          </div>
          <button
            className="ec-btn-primary"
            onClick={() => {
              setCreateOpen(true);
              setCreatedToken(null);
            }}
            data-testid="scim-new"
          >
            <Plus size={16} /> Generate token
          </button>
        </header>

        <div className="rounded-lg bg-surface-muted/40 p-3 text-xs">
          <p className="text-ink-subtle">SCIM 2.0 base URL</p>
          <p className="mt-1 font-mono break-all" data-testid="scim-base-url">{scimBaseUrl()}</p>
        </div>

        {tokensQ.isLoading ? (
          <p className="text-sm text-ink-muted">Loading tokens…</p>
        ) : (tokensQ.data?.length ?? 0) === 0 ? (
          <p className="py-4 text-center text-sm text-ink-muted">No tokens yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-ink-subtle">
                <th className="py-2 pr-3">Name</th>
                <th className="py-2 pr-3">Created</th>
                <th className="py-2 pr-3">Last used</th>
                <th className="py-2 pr-3">Expires</th>
                <th className="py-2 pr-3" />
              </tr>
            </thead>
            <tbody>
              {tokensQ.data!.map((t) => (
                <tr key={t.id} className="border-b border-border/40">
                  <td className="py-2 pr-3">{t.name}</td>
                  <td className="py-2 pr-3 text-ink-muted">{formatDate(t.created_at)}</td>
                  <td className="py-2 pr-3 text-ink-muted">
                    {t.last_used_at ? formatDateTime(t.last_used_at) : '—'}
                  </td>
                  <td className="py-2 pr-3 text-ink-muted">{formatDate(t.expires_at)}</td>
                  <td className="py-2 pr-3 text-right">
                    {t.revoked_at ? (
                      <span className="ec-badge-rose">revoked</span>
                    ) : (
                      <button
                        className="rounded p-1.5 text-rose-600 hover:bg-rose-500/10"
                        onClick={() => revoke.mutate(t.id)}
                        title="Revoke"
                      >
                        <Trash2 size={15} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {createOpen ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-ink/40 backdrop-blur-sm p-4">
          <div className="ec-card w-full max-w-md p-5 relative">
            <button
              className="absolute right-2 top-2 rounded-md p-1.5 text-ink-muted hover:bg-surface-muted"
              onClick={() => setCreateOpen(false)}
              aria-label="Close"
            >
              <X size={16} />
            </button>
            {!createdToken ? (
              <>
                <h3 className="text-lg font-semibold">Generate SCIM token</h3>
                <p className="mt-1 text-sm text-ink-muted">Shown only once. Store it safely.</p>
                <div className="mt-4 space-y-3">
                  <div>
                    <label className="ec-label" htmlFor="scim-name">Label</label>
                    <input
                      id="scim-name"
                      className="ec-input"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Okta production"
                      data-testid="scim-name"
                    />
                  </div>
                  <div>
                    <label className="ec-label" htmlFor="scim-ttl">TTL (days)</label>
                    <input
                      id="scim-ttl"
                      className="ec-input"
                      type="number"
                      min={1}
                      max={3650}
                      value={ttlDays}
                      onChange={(e) => setTtlDays(parseInt(e.target.value, 10) || 365)}
                    />
                  </div>
                  <button
                    className="ec-btn-primary w-full"
                    disabled={!name || create.isPending}
                    onClick={() => create.mutate()}
                    data-testid="scim-create"
                  >
                    Generate
                  </button>
                </div>
              </>
            ) : (
              <>
                <h3 className="text-lg font-semibold">Copy this token now</h3>
                <p className="mt-1 text-sm text-amber-600">You won&apos;t be able to see it again.</p>
                <div className="ec-card mt-4 bg-surface-muted/60 p-3 text-xs font-mono break-all">
                  {createdToken}
                </div>
                <div className="mt-3 flex gap-2">
                  <button
                    className="ec-btn-secondary flex-1"
                    onClick={() => {
                      navigator.clipboard.writeText(createdToken);
                      toast.success('Copied');
                    }}
                  >
                    <Copy size={16} /> Copy
                  </button>
                  <button className="ec-btn-primary flex-1" onClick={() => setCreateOpen(false)}>Done</button>
                </div>
              </>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
