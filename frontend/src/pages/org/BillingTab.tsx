import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useState } from 'react';
import { CreditCard, ExternalLink, ReceiptText, Sparkles, X } from 'lucide-react';
import { billingApi, type PlanCatalogItem } from '../../lib/billing';
import { useAuthStore } from '../../store/auth';
import { formatDate } from '../../lib/format';

export function BillingTab() {
  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasRole('Admin'));
  const tenant = useAuthStore((s) => s.tenant);

  const subQ = useQuery({ queryKey: ['billing', 'subscription'], queryFn: () => billingApi.getSubscription() });
  const plansQ = useQuery({ queryKey: ['billing', 'plans'], queryFn: () => billingApi.listPlans() });
  const usageQ = useQuery({ queryKey: ['billing', 'usage'], queryFn: () => billingApi.usage() });
  const invoicesQ = useQuery({ queryKey: ['billing', 'invoices'], queryFn: () => billingApi.invoices() });

  const [showUpgrade, setShowUpgrade] = useState(false);

  const portal = useMutation({
    mutationFn: () => billingApi.openPortal(window.location.origin),
    onSuccess: (data) => {
      if (data.self_managed) {
        toast('Stripe is not configured. Billing is self-managed.');
      } else {
        window.open(data.portal_url, '_blank', 'noopener,noreferrer');
      }
    },
    onError: () => toast.error('Could not open billing portal'),
  });

  const checkout = useMutation({
    mutationFn: (plan: 'core' | 'edu' | 'verticals') =>
      billingApi.startCheckout({
        plan,
        interval: 'month',
        success_url: `${window.location.origin}/#/org/billing?ok=1`,
        cancel_url: `${window.location.origin}/#/org/billing`,
      }),
    onSuccess: (data) => {
      window.location.href = data.checkout_url;
    },
    onError: () => toast.error('Could not start checkout'),
  });

  const resume = useMutation({
    mutationFn: () => billingApi.resume(),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['billing'] });
      toast.success(data.message);
    },
    onError: () => toast.error('Could not resume'),
  });

  const cancel = useMutation({
    mutationFn: () => billingApi.cancel(),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['billing'] });
      toast.success(data.message);
    },
    onError: () => toast.error('Could not cancel'),
  });

  const sub = subQ.data;
  const trialEnds = sub?.trial_end ?? tenant?.trial_ends_at ?? null;
  let trialDaysLeft: number | null = null;
  if (trialEnds && sub?.status === 'trialing') {
    const diff = new Date(trialEnds).getTime() - Date.now();
    trialDaysLeft = Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
  }

  return (
    <div className="space-y-4">
      {/* Hero card */}
      <div className="ec-card p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-ink-subtle">Current plan</p>
            <h2 className="mt-1 text-2xl font-semibold">
              {sub?.plan ?? tenant?.plan ?? 'evaluation'}
            </h2>
            <p className="mt-1 text-sm text-ink-muted">
              {sub?.status ? <span className="ec-badge-green">{sub.status}</span> : <span className="ec-badge-amber">no active subscription</span>}
              {sub?.current_period_end ? (
                <span className="ml-2 text-ink-muted">
                  Next billing: {formatDate(sub.current_period_end)}
                </span>
              ) : null}
              {trialDaysLeft !== null ? (
                <span className="ml-2 text-amber-600">Trial ends in {trialDaysLeft} day{trialDaysLeft === 1 ? '' : 's'}</span>
              ) : null}
            </p>
          </div>
          {isAdmin ? (
            <div className="flex flex-wrap gap-2">
              <button className="ec-btn-secondary" onClick={() => setShowUpgrade(true)} data-testid="billing-upgrade">
                <Sparkles size={16} /> Upgrade plan
              </button>
              <button
                className="ec-btn-secondary"
                onClick={() => portal.mutate()}
                disabled={portal.isPending}
                data-testid="billing-portal"
              >
                <ExternalLink size={16} /> Manage subscription
              </button>
              {sub?.cancel_at_period_end ? (
                <button className="ec-btn-primary" onClick={() => resume.mutate()} disabled={resume.isPending}>
                  Resume
                </button>
              ) : sub ? (
                <button className="ec-btn-secondary text-rose-600" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
                  Cancel
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      {/* Usage */}
      <div className="ec-card p-5">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <CreditCard size={18} /> Usage this period
        </h3>
        {usageQ.isLoading ? (
          <p className="text-sm text-ink-muted">Loading…</p>
        ) : usageQ.data ? (
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <div>
              <p className="text-xs text-ink-subtle">AI spend</p>
              <div className="mt-1 flex items-baseline gap-1">
                <span className="text-xl font-semibold">${usageQ.data.ai_paid_usd_this_period.toFixed(2)}</span>
                <span className="text-sm text-ink-muted">/ ${usageQ.data.ai_monthly_cap_usd.toFixed(2)} cap</span>
              </div>
              <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-surface-muted">
                <div
                  className="h-full bg-brand-600"
                  style={{
                    width: `${Math.min(
                      100,
                      usageQ.data.ai_monthly_cap_usd > 0
                        ? (usageQ.data.ai_paid_usd_this_period / usageQ.data.ai_monthly_cap_usd) * 100
                        : 0,
                    )}%`,
                  }}
                />
              </div>
            </div>
            <div>
              <p className="text-xs text-ink-subtle">Seats</p>
              <p className="mt-1 text-xl font-semibold">
                {sub?.seat_count ?? 0} / {sub?.seat_quota ?? '∞'}
              </p>
              {sub?.overage_seats ? (
                <p className="text-sm text-amber-600">{sub.overage_seats} over quota</p>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>

      {/* Invoices */}
      <div className="ec-card p-5">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <ReceiptText size={18} /> Invoices
        </h3>
        {invoicesQ.isLoading ? (
          <p className="mt-3 text-sm text-ink-muted">Loading…</p>
        ) : invoicesQ.data?.self_managed ? (
          <p className="mt-3 text-sm text-ink-muted">Stripe is not configured. Invoices are self-managed.</p>
        ) : invoicesQ.data && invoicesQ.data.invoices.length > 0 ? (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-ink-subtle">
                  <th className="py-2 pr-3">Number</th>
                  <th className="py-2 pr-3">Date</th>
                  <th className="py-2 pr-3">Status</th>
                  <th className="py-2 pr-3 text-right">Amount</th>
                  <th className="py-2 pr-3" />
                </tr>
              </thead>
              <tbody>
                {invoicesQ.data.invoices.map((inv) => (
                  <tr key={inv.id} className="border-b border-border/40">
                    <td className="py-2 pr-3 font-mono text-xs">{inv.number ?? inv.id}</td>
                    <td className="py-2 pr-3 text-ink-muted">{formatDate(inv.created * 1000)}</td>
                    <td className="py-2 pr-3"><span className="ec-badge-green">{inv.status}</span></td>
                    <td className="py-2 pr-3 text-right">${inv.amount_paid_usd.toFixed(2)}</td>
                    <td className="py-2 pr-3 text-right">
                      {inv.hosted_invoice_url ? (
                        <a className="text-brand-600 hover:underline" href={inv.hosted_invoice_url} target="_blank" rel="noreferrer">
                          View
                        </a>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-3 text-sm text-ink-muted">No invoices yet.</p>
        )}
      </div>

      {showUpgrade ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-ink/40 backdrop-blur-sm p-4">
          <div className="ec-card w-full max-w-3xl p-5 relative">
            <button
              className="absolute right-2 top-2 rounded-md p-1.5 text-ink-muted hover:bg-surface-muted"
              onClick={() => setShowUpgrade(false)}
              aria-label="Close"
            >
              <X size={16} />
            </button>
            <h3 className="text-lg font-semibold">Choose a plan</h3>
            {plansQ.isLoading ? (
              <p className="mt-3 text-sm text-ink-muted">Loading plans…</p>
            ) : (
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                {plansQ.data?.plans.map((plan: PlanCatalogItem) => (
                  <div key={plan.plan} className="rounded-xl border border-border p-4">
                    <p className="text-sm font-semibold capitalize">{plan.plan}</p>
                    <p className="mt-1 text-2xl font-semibold">{plan.formatted_monthly}</p>
                    <p className="mt-1 text-xs text-ink-subtle">Includes {plan.base_seats} seats</p>
                    <button
                      className="ec-btn-primary mt-3 w-full"
                      onClick={() => checkout.mutate(plan.plan as 'core' | 'edu' | 'verticals')}
                      disabled={checkout.isPending}
                    >
                      Choose {plan.plan}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
