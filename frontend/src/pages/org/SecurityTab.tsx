import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Plus, Save, Shield, Trash2, X, Zap } from 'lucide-react';
import {
  securityPoliciesApi,
  type AuditStreamIn,
  type AuditStreamType,
} from '../../lib/security_policies';
import { useAuthStore } from '../../store/auth';
import { formatDateTime } from '../../lib/utils';
import { PermissionDenied } from './OrgLayout';

const STREAM_TYPES: { value: AuditStreamType; label: string }[] = [
  { value: 'webhook', label: 'Generic webhook' },
  { value: 'splunk_hec', label: 'Splunk HEC' },
  { value: 'datadog_logs', label: 'Datadog Logs' },
  { value: 'sumo_logic', label: 'Sumo Logic' },
];

export function SecurityTab() {
  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasRole('Admin'));

  const policyQ = useQuery({
    queryKey: ['security', 'policy'],
    queryFn: () => securityPoliciesApi.getPolicy(),
    enabled: isAdmin,
  });
  const destsQ = useQuery({
    queryKey: ['security', 'destinations'],
    queryFn: () => securityPoliciesApi.listDestinations(),
    enabled: isAdmin,
  });

  const [cidrs, setCidrs] = useState<string[]>([]);
  const [newCidr, setNewCidr] = useState('');
  const [enforced, setEnforced] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (policyQ.data && !hydrated) {
      setCidrs(policyQ.data.ip_allowlist_cidrs);
      setEnforced(policyQ.data.ip_allowlist_enforced);
      setHydrated(true);
    }
  }, [policyQ.data, hydrated]);

  const saveAllowlist = useMutation({
    mutationFn: () => securityPoliciesApi.updateIpAllowlist({ cidrs, enforced }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['security', 'policy'] });
      toast.success('IP allowlist updated');
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Could not save'),
  });

  function addCidr() {
    const c = newCidr.trim();
    if (!c) return;
    if (cidrs.includes(c)) {
      toast.error('Already in list');
      return;
    }
    setCidrs((cs) => [...cs, c]);
    setNewCidr('');
  }

  // Audit stream destinations
  const [createDest, setCreateDest] = useState(false);
  const [dest, setDest] = useState<AuditStreamIn>({
    name: '',
    destination_type: 'webhook',
    url: '',
    credentials: '',
    is_active: true,
  });

  const createDestM = useMutation({
    mutationFn: () => securityPoliciesApi.createDestination(dest),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['security', 'destinations'] });
      setCreateDest(false);
      setDest({ name: '', destination_type: 'webhook', url: '', credentials: '', is_active: true });
      toast.success('Destination added');
    },
  });

  const delDest = useMutation({
    mutationFn: (id: string) => securityPoliciesApi.deleteDestination(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['security', 'destinations'] });
      toast.success('Destination removed');
    },
  });

  const testDest = useMutation({
    mutationFn: (id: string) => securityPoliciesApi.testDestination(id),
    onSuccess: (data) => {
      if (data.ok) toast.success('Test event delivered');
      else toast.error(data.error ?? 'Test failed');
    },
  });

  if (!isAdmin) return <PermissionDenied what="manage security policies" />;

  return (
    <div className="space-y-4">
      <div className="ec-card p-5 space-y-4">
        <header>
          <h2 className="text-lg font-semibold flex items-center gap-2"><Shield size={18} /> IP allowlist</h2>
          <p className="text-sm text-ink-muted">Restrict admin sign-in to known networks.</p>
        </header>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enforced}
            onChange={(e) => setEnforced(e.target.checked)}
            data-testid="ip-enforce"
          />
          Enforce IP allowlist
        </label>

        <div className="space-y-2">
          <label className="ec-label">CIDR blocks</label>
          {cidrs.length === 0 ? (
            <p className="text-xs text-ink-muted">No CIDR blocks configured.</p>
          ) : (
            <ul className="space-y-1">
              {cidrs.map((c) => (
                <li key={c} className="flex items-center justify-between rounded-lg border border-border bg-surface-muted/30 px-3 py-1.5 text-sm">
                  <span className="font-mono">{c}</span>
                  <button
                    className="rounded p-1 text-rose-600 hover:bg-rose-500/10"
                    onClick={() => setCidrs((cs) => cs.filter((x) => x !== c))}
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex gap-2">
            <input
              className="ec-input flex-1 font-mono"
              placeholder="10.0.0.0/24"
              value={newCidr}
              onChange={(e) => setNewCidr(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  addCidr();
                }
              }}
              data-testid="ip-cidr-input"
            />
            <button className="ec-btn-secondary" onClick={addCidr}><Plus size={16} /></button>
          </div>
          {enforced && cidrs.length > 0 ? (
            <p className="rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-700">
              Warning: make sure your current IP is in the list, or you may lock yourself out.
            </p>
          ) : null}
        </div>

        <div className="flex justify-end">
          <button
            className="ec-btn-primary"
            onClick={() => saveAllowlist.mutate()}
            disabled={saveAllowlist.isPending}
            data-testid="ip-save"
          >
            <Save size={16} /> {saveAllowlist.isPending ? 'Saving…' : 'Save allowlist'}
          </button>
        </div>
      </div>

      <div className="ec-card p-5 space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Audit stream destinations</h2>
            <p className="text-sm text-ink-muted">Mirror audit events to your SIEM in real time.</p>
          </div>
          <button className="ec-btn-primary" onClick={() => setCreateDest(true)} data-testid="dest-new">
            <Plus size={16} /> Add destination
          </button>
        </div>

        {destsQ.isLoading ? (
          <p className="text-sm text-ink-muted">Loading…</p>
        ) : (destsQ.data?.length ?? 0) === 0 ? (
          <p className="py-4 text-center text-sm text-ink-muted">No destinations configured.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-ink-subtle">
                <th className="py-2 pr-3">Name</th>
                <th className="py-2 pr-3">Type</th>
                <th className="py-2 pr-3">URL</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2 pr-3">Last delivered</th>
                <th className="py-2 pr-3" />
              </tr>
            </thead>
            <tbody>
              {destsQ.data!.map((d) => (
                <tr key={d.id} className="border-b border-border/40">
                  <td className="py-2 pr-3 font-medium">{d.name}</td>
                  <td className="py-2 pr-3 text-ink-muted">{d.destination_type}</td>
                  <td className="py-2 pr-3 text-ink-muted truncate max-w-[240px]">{d.url}</td>
                  <td className="py-2 pr-3">
                    {d.is_active ? <span className="ec-badge-green">active</span> : <span className="ec-badge-amber">paused</span>}
                  </td>
                  <td className="py-2 pr-3 text-ink-muted">
                    {d.last_success_at ? formatDateTime(d.last_success_at) : '—'}
                  </td>
                  <td className="py-2 pr-3 text-right">
                    <button
                      className="rounded p-1.5 text-brand-600 hover:bg-brand-600/10"
                      onClick={() => testDest.mutate(d.id)}
                      title="Test"
                    >
                      <Zap size={15} />
                    </button>
                    <button
                      className="rounded p-1.5 text-rose-600 hover:bg-rose-500/10"
                      onClick={() => delDest.mutate(d.id)}
                      title="Remove"
                    >
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {createDest ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-ink/40 backdrop-blur-sm p-4">
          <div className="ec-card w-full max-w-md p-5 relative">
            <button
              className="absolute right-2 top-2 rounded-md p-1.5 text-ink-muted hover:bg-surface-muted"
              onClick={() => setCreateDest(false)}
              aria-label="Close"
            >
              <X size={16} />
            </button>
            <h3 className="text-lg font-semibold">Add audit stream destination</h3>
            <div className="mt-4 space-y-3">
              <div>
                <label className="ec-label" htmlFor="dest-name">Name</label>
                <input
                  id="dest-name"
                  className="ec-input"
                  value={dest.name}
                  onChange={(e) => setDest((d) => ({ ...d, name: e.target.value }))}
                  data-testid="dest-name"
                />
              </div>
              <div>
                <label className="ec-label" htmlFor="dest-type">Type</label>
                <select
                  id="dest-type"
                  className="ec-input"
                  value={dest.destination_type}
                  onChange={(e) => setDest((d) => ({ ...d, destination_type: e.target.value as AuditStreamType }))}
                >
                  {STREAM_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="ec-label" htmlFor="dest-url">URL</label>
                <input
                  id="dest-url"
                  className="ec-input"
                  value={dest.url}
                  onChange={(e) => setDest((d) => ({ ...d, url: e.target.value }))}
                  data-testid="dest-url"
                />
              </div>
              <div>
                <label className="ec-label" htmlFor="dest-creds">Credentials (token or API key)</label>
                <input
                  id="dest-creds"
                  className="ec-input"
                  type="password"
                  value={dest.credentials ?? ''}
                  onChange={(e) => setDest((d) => ({ ...d, credentials: e.target.value }))}
                />
              </div>
              <button
                className="ec-btn-primary w-full"
                onClick={() => createDestM.mutate()}
                disabled={createDestM.isPending || !dest.name || !dest.url}
                data-testid="dest-save"
              >
                {createDestM.isPending ? 'Saving…' : 'Add destination'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
