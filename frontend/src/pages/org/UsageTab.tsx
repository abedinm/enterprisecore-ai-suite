import { useQuery } from '@tanstack/react-query';
import { Activity, DollarSign, HardDrive, Users } from 'lucide-react';
import { tenantApi } from '../../lib/tenant';

export function UsageTab() {
  const usageQ = useQuery({ queryKey: ['tenant', 'usage'], queryFn: () => tenantApi.usage() });

  if (usageQ.isLoading) return <p className="text-sm text-ink-muted">Loading usage…</p>;
  if (usageQ.isError || !usageQ.data) {
    return (
      <div className="ec-card border-rose-300 bg-rose-50 p-4 text-sm text-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
        Could not load usage.
      </div>
    );
  }

  const { user_count, storage_mb, ai_spend_ytd_usd } = usageQ.data;

  return (
    <div className="space-y-4">
      <div className="ec-card p-5">
        <header>
          <h2 className="text-lg font-semibold flex items-center gap-2"><Activity size={18} /> Usage snapshot</h2>
          <p className="text-sm text-ink-muted">Read-only metrics for the current tenant.</p>
        </header>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <Tile icon={Users} label="Users" value={user_count.toString()} />
          <Tile
            icon={HardDrive}
            label="Storage"
            value={`${storage_mb.toFixed(1)} MB`}
            note={storage_mb === 0 ? 'Storage accounting not yet wired up.' : undefined}
          />
          <Tile icon={DollarSign} label="AI spend YTD" value={`$${ai_spend_ytd_usd.toFixed(2)}`} />
        </div>
        <p className="mt-6 text-xs text-ink-subtle">
          Trend charts will land once Recharts is added to this page bundle.
        </p>
      </div>
    </div>
  );
}

function Tile({
  icon: Icon, label, value, note,
}: { icon: typeof Activity; label: string; value: string; note?: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface-muted/30 p-4">
      <div className="flex items-center justify-between">
        <p className="text-xs uppercase tracking-wider text-ink-subtle">{label}</p>
        <Icon size={16} className="text-brand-600" />
      </div>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
      {note ? <p className="mt-1 text-[11px] text-ink-subtle">{note}</p> : null}
    </div>
  );
}
