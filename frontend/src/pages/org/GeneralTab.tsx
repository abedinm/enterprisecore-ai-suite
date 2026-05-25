import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Save } from 'lucide-react';
import { tenantApi, type TenantUpdate } from '../../lib/tenant';
import { useAuthStore } from '../../store/auth';
import { PermissionDenied } from './OrgLayout';

export function GeneralTab() {
  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasRole('Admin'));
  const tenantQ = useQuery({ queryKey: ['tenant', 'me'], queryFn: () => tenantApi.me() });

  const [form, setForm] = useState<TenantUpdate>({});
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (tenantQ.data && !hydrated) {
      setForm({
        name: tenantQ.data.name,
        primary_contact_email: tenantQ.data.primary_contact_email,
        timezone: tenantQ.data.timezone,
        currency: tenantQ.data.currency,
      });
      setHydrated(true);
    }
  }, [tenantQ.data, hydrated]);

  const save = useMutation({
    mutationFn: () => tenantApi.updateMe(form),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['tenant', 'me'] });
      useAuthStore.getState().setTenant(data);
      toast.success('Saved');
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? 'Failed to save');
    },
  });

  if (tenantQ.isLoading || !tenantQ.data) return <p className="text-sm text-ink-muted">Loading tenant…</p>;
  if (tenantQ.isError) {
    return (
      <div className="ec-card border-rose-300 bg-rose-50 p-4 text-sm text-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
        Could not load tenant.
      </div>
    );
  }
  const tenantData = tenantQ.data;

  return (
    <div className="space-y-4">
      <div className="ec-card space-y-4 p-5">
        <header>
          <h2 className="text-lg font-semibold">General</h2>
          <p className="text-sm text-ink-muted">Identity and locale of your organization.</p>
        </header>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="ec-label" htmlFor="t-name">Organization name</label>
            <input
              id="t-name"
              className="ec-input"
              value={form.name ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              disabled={!isAdmin}
              data-testid="org-name"
            />
          </div>
          <div>
            <label className="ec-label">Slug</label>
            <input
              className="ec-input opacity-70"
              value={tenantData.slug}
              disabled
              readOnly
            />
            <p className="mt-1 text-[11px] text-ink-subtle">Slug cannot be changed after signup.</p>
          </div>
          <div>
            <label className="ec-label" htmlFor="t-email">Primary contact email</label>
            <input
              id="t-email"
              type="email"
              className="ec-input"
              value={form.primary_contact_email ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, primary_contact_email: e.target.value }))}
              disabled={!isAdmin}
              data-testid="org-contact-email"
            />
          </div>
          <div>
            <label className="ec-label" htmlFor="t-tz">Timezone</label>
            <input
              id="t-tz"
              className="ec-input"
              value={form.timezone ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))}
              disabled={!isAdmin}
              placeholder="UTC"
              data-testid="org-timezone"
            />
          </div>
          <div>
            <label className="ec-label" htmlFor="t-curr">Currency (ISO 4217)</label>
            <input
              id="t-curr"
              className="ec-input uppercase"
              value={form.currency ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, currency: e.target.value.toUpperCase().slice(0, 3) }))}
              disabled={!isAdmin}
              placeholder="USD"
              maxLength={3}
              minLength={3}
              data-testid="org-currency"
            />
          </div>
          <div>
            <label className="ec-label">Plan</label>
            <input className="ec-input opacity-70" value={tenantData.plan} disabled readOnly />
          </div>
        </div>

        {isAdmin ? (
          <div className="flex justify-end">
            <button
              className="ec-btn-primary"
              onClick={() => save.mutate()}
              disabled={save.isPending}
              data-testid="org-save"
            >
              <Save size={16} /> {save.isPending ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        ) : (
          <PermissionDenied what="modify organization settings" />
        )}
      </div>
    </div>
  );
}
