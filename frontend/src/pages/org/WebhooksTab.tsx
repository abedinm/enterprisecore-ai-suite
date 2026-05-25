import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Copy, Plus, RefreshCw, Trash2, Webhook, X, Zap } from 'lucide-react';
import { webhooksApi, type WebhookSubscriptionIn } from '../../lib/webhooks';
import { useAuthStore } from '../../store/auth';
import { formatDateTime } from '../../lib/format';
import { PermissionDenied } from './OrgLayout';

export function WebhooksTab() {
  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasRole('Admin', 'Manager'));

  const subsQ = useQuery({ queryKey: ['webhooks', 'subs'], queryFn: () => webhooksApi.list(), enabled: isAdmin });
  const eventsQ = useQuery({
    queryKey: ['webhooks', 'events'],
    queryFn: () => webhooksApi.eventTypes(),
    enabled: isAdmin,
  });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [createdSecret, setCreatedSecret] = useState<string | null>(null);
  const [form, setForm] = useState<WebhookSubscriptionIn>({
    name: '',
    url: '',
    event_types: ['*'],
    is_active: true,
  });

  const deliveriesQ = useQuery({
    queryKey: ['webhooks', 'deliveries', selectedId],
    queryFn: () => webhooksApi.deliveries(selectedId!),
    enabled: !!selectedId,
  });

  const create = useMutation({
    mutationFn: () => webhooksApi.create(form),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['webhooks', 'subs'] });
      setCreatedSecret(data.secret);
      setForm({ name: '', url: '', event_types: ['*'], is_active: true });
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Could not create'),
  });

  const del = useMutation({
    mutationFn: (id: string) => webhooksApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['webhooks', 'subs'] });
      if (selectedId) setSelectedId(null);
      toast.success('Webhook deleted');
    },
  });

  const test = useMutation({
    mutationFn: (id: string) => webhooksApi.test(id),
    onSuccess: () => toast.success('Test event queued'),
  });

  const retry = useMutation({
    mutationFn: (id: string) => webhooksApi.retry(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['webhooks', 'deliveries'] });
      toast.success('Re-queued');
    },
  });

  if (!isAdmin) return <PermissionDenied what="manage webhooks" />;

  return (
    <div className="space-y-4">
      <div className="ec-card p-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2"><Webhook size={18} /> Webhooks</h2>
            <p className="text-sm text-ink-muted">Outbound subscriptions for system events.</p>
          </div>
          <button
            className="ec-btn-primary"
            onClick={() => {
              setCreateOpen(true);
              setCreatedSecret(null);
            }}
            data-testid="webhook-new"
          >
            <Plus size={16} /> New subscription
          </button>
        </div>

        {subsQ.isLoading ? (
          <p className="mt-4 text-sm text-ink-muted">Loading…</p>
        ) : (subsQ.data?.length ?? 0) === 0 ? (
          <p className="mt-4 py-4 text-center text-sm text-ink-muted">No webhooks yet.</p>
        ) : (
          <table className="mt-4 w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-ink-subtle">
                <th className="py-2 pr-3">Name</th>
                <th className="py-2 pr-3">URL</th>
                <th className="py-2 pr-3">Events</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2 pr-3">Last delivered</th>
                <th className="py-2 pr-3" />
              </tr>
            </thead>
            <tbody>
              {subsQ.data!.map((s) => (
                <tr
                  key={s.id}
                  className={`cursor-pointer border-b border-border/40 hover:bg-surface-muted/30 ${
                    selectedId === s.id ? 'bg-brand-600/5' : ''
                  }`}
                  onClick={() => setSelectedId(s.id)}
                >
                  <td className="py-2 pr-3 font-medium">{s.name}</td>
                  <td className="py-2 pr-3 text-ink-muted truncate max-w-[200px]">{s.url}</td>
                  <td className="py-2 pr-3">
                    <div className="flex flex-wrap gap-1">
                      {s.event_types.slice(0, 3).map((et) => (
                        <span key={et} className="ec-badge-green text-[10px]">{et}</span>
                      ))}
                      {s.event_types.length > 3 ? <span className="text-xs text-ink-muted">+{s.event_types.length - 3}</span> : null}
                    </div>
                  </td>
                  <td className="py-2 pr-3">
                    {s.is_active ? <span className="ec-badge-green">active</span> : <span className="ec-badge-amber">paused</span>}
                  </td>
                  <td className="py-2 pr-3 text-ink-muted">
                    {s.last_delivered_at ? formatDateTime(s.last_delivered_at) : '—'}
                  </td>
                  <td className="py-2 pr-3 text-right">
                    <button
                      className="rounded p-1.5 text-brand-600 hover:bg-brand-600/10"
                      onClick={(e) => {
                        e.stopPropagation();
                        test.mutate(s.id);
                      }}
                      title="Fire test event"
                    >
                      <Zap size={15} />
                    </button>
                    <button
                      className="rounded p-1.5 text-rose-600 hover:bg-rose-500/10"
                      onClick={(e) => {
                        e.stopPropagation();
                        del.mutate(s.id);
                      }}
                      title="Delete"
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

      {selectedId ? (
        <div className="ec-card p-5">
          <h3 className="text-lg font-semibold">Recent deliveries</h3>
          {deliveriesQ.isLoading ? (
            <p className="text-sm text-ink-muted">Loading deliveries…</p>
          ) : (deliveriesQ.data?.length ?? 0) === 0 ? (
            <p className="mt-3 text-sm text-ink-muted">No deliveries yet.</p>
          ) : (
            <table className="mt-3 w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-ink-subtle">
                  <th className="py-2 pr-3">Time</th>
                  <th className="py-2 pr-3">Event</th>
                  <th className="py-2 pr-3">Status</th>
                  <th className="py-2 pr-3">Attempt</th>
                  <th className="py-2 pr-3" />
                </tr>
              </thead>
              <tbody>
                {deliveriesQ.data!.map((d) => {
                  const failed = d.response_status === null || (d.response_status >= 400);
                  return (
                    <tr key={d.id} className="border-b border-border/40">
                      <td className="py-2 pr-3 text-ink-muted">{formatDateTime(d.created_at)}</td>
                      <td className="py-2 pr-3 font-mono text-xs">{d.event_type}</td>
                      <td className="py-2 pr-3">
                        {failed ? (
                          <span className="ec-badge-rose">{d.response_status ?? 'error'}</span>
                        ) : (
                          <span className="ec-badge-green">{d.response_status}</span>
                        )}
                      </td>
                      <td className="py-2 pr-3 text-ink-muted">{d.attempt_number}</td>
                      <td className="py-2 pr-3 text-right">
                        {failed ? (
                          <button
                            className="rounded p-1.5 text-brand-600 hover:bg-brand-600/10"
                            onClick={() => retry.mutate(d.id)}
                            title="Retry"
                          >
                            <RefreshCw size={15} />
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      ) : null}

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
            {!createdSecret ? (
              <>
                <h3 className="text-lg font-semibold">New webhook subscription</h3>
                <div className="mt-4 space-y-3">
                  <div>
                    <label className="ec-label" htmlFor="wh-name">Name</label>
                    <input
                      id="wh-name"
                      className="ec-input"
                      value={form.name}
                      onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                      data-testid="wh-name"
                    />
                  </div>
                  <div>
                    <label className="ec-label" htmlFor="wh-url">Endpoint URL (https)</label>
                    <input
                      id="wh-url"
                      className="ec-input"
                      type="url"
                      value={form.url}
                      onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
                      placeholder="https://example.com/webhook"
                      data-testid="wh-url"
                    />
                  </div>
                  <div>
                    <label className="ec-label">Event types</label>
                    <div className="max-h-48 overflow-y-auto rounded-lg border border-border p-2">
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={form.event_types?.includes('*') ?? false}
                          onChange={(e) =>
                            setForm((f) => ({ ...f, event_types: e.target.checked ? ['*'] : [] }))
                          }
                          data-testid="wh-event-all"
                        />
                        <span className="font-semibold">All events (*)</span>
                      </label>
                      {!form.event_types?.includes('*') && eventsQ.data
                        ? eventsQ.data.map((ev) => (
                            <label key={ev.type} className="flex items-center gap-2 text-xs">
                              <input
                                type="checkbox"
                                checked={form.event_types?.includes(ev.type) ?? false}
                                onChange={(e) =>
                                  setForm((f) => ({
                                    ...f,
                                    event_types: e.target.checked
                                      ? [...(f.event_types ?? []), ev.type]
                                      : (f.event_types ?? []).filter((t) => t !== ev.type),
                                  }))
                                }
                              />
                              <span className="font-mono">{ev.type}</span>
                              <span className="text-ink-subtle">{ev.module}</span>
                            </label>
                          ))
                        : null}
                    </div>
                  </div>
                  <div>
                    <label className="ec-label" htmlFor="wh-secret">Optional signing secret</label>
                    <input
                      id="wh-secret"
                      className="ec-input"
                      type="text"
                      value={form.secret ?? ''}
                      onChange={(e) => setForm((f) => ({ ...f, secret: e.target.value || null }))}
                      placeholder="Leave blank to auto-generate"
                    />
                  </div>
                  <button
                    className="ec-btn-primary w-full"
                    onClick={() => create.mutate()}
                    disabled={create.isPending || !form.name || !form.url}
                    data-testid="wh-create"
                  >
                    Create subscription
                  </button>
                </div>
              </>
            ) : (
              <>
                <h3 className="text-lg font-semibold">Subscription created</h3>
                <p className="mt-1 text-sm text-amber-600">Save this secret. It won&apos;t be shown again.</p>
                <div className="ec-card mt-4 bg-surface-muted/60 p-3 text-xs font-mono break-all">
                  {createdSecret}
                </div>
                <div className="mt-3 flex gap-2">
                  <button
                    className="ec-btn-secondary flex-1"
                    onClick={() => {
                      navigator.clipboard.writeText(createdSecret);
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
