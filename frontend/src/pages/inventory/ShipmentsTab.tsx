import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit3, X, Truck, MapPin } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';
import { formatDate, formatDateTime } from '../../lib/utils';
import { Shipment, ShipmentEvent, SHIPMENT_STATUSES, STATUS_BADGE } from './types';

export function ShipmentsTab() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Shipment | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [directionFilter, setDirectionFilter] = useState('');
  const [selected, setSelected] = useState<string | null>(null);

  const shipments = useQuery({
    queryKey: ['inventory', 'shipments', statusFilter, directionFilter],
    queryFn: async () => (await api.get<Shipment[]>('/inventory/shipments', {
      params: { ...(statusFilter ? { status: statusFilter } : {}), ...(directionFilter ? { direction: directionFilter } : {}) },
    })).data,
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/inventory/shipments/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventory', 'shipments'] }),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Shipment Tracker</p>
          <p className="text-sm text-ink-muted">{shipments.data?.length ?? 0} shipments.</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="ec-label">Status</label>
            <select className="ec-input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All</option>
              {SHIPMENT_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="ec-label">Direction</label>
            <select className="ec-input" value={directionFilter} onChange={(e) => setDirectionFilter(e.target.value)}>
              <option value="">All</option>
              <option value="inbound">Inbound</option>
              <option value="outbound">Outbound</option>
            </select>
          </div>
          <button className="ec-btn-primary" onClick={() => { setEditing(null); setShowForm(true); }}><Plus size={16} /> New shipment</button>
        </div>
      </div>

      {(showForm || editing) && (
        <ShipmentForm
          editing={editing}
          onSaved={() => { setShowForm(false); setEditing(null); qc.invalidateQueries({ queryKey: ['inventory', 'shipments'] }); }}
          onCancel={() => { setShowForm(false); setEditing(null); }}
        />
      )}

      <div className="grid gap-3 lg:grid-cols-[1.4fr_1fr]">
        <div className="ec-card overflow-x-auto">
          <div className="border-b border-border bg-surface-muted px-3 py-2 text-sm font-semibold">Shipments</div>
          <table className="ec-table">
            <thead><tr><th>Tracking</th><th>Carrier</th><th>Status</th><th>Dir</th><th>Expected</th><th>Delivered</th><th></th></tr></thead>
            <tbody>
              {shipments.data?.length ? shipments.data.map((s) => (
                <tr key={s.id} className={selected === s.id ? 'bg-surface-muted' : ''}>
                  <td className="font-mono cursor-pointer text-xs" onClick={() => setSelected(s.id)}>{s.tracking_number}</td>
                  <td>{s.carrier ?? '—'}</td>
                  <td><span className={STATUS_BADGE[s.status] ?? 'ec-badge'}>{s.status}</span></td>
                  <td><span className="ec-badge">{s.direction}</span></td>
                  <td>{s.expected_date ? formatDate(s.expected_date) : '—'}</td>
                  <td>{s.delivered_date ? formatDate(s.delivered_date) : '—'}</td>
                  <td className="text-right whitespace-nowrap">
                    <button className="ec-btn-ghost" onClick={() => { setEditing(s); setShowForm(true); }}><Edit3 size={14} /></button>
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete shipment?')) remove.mutate(s.id); }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              )) : <tr><td colSpan={7} className="py-10 text-center text-ink-muted">No shipments yet.</td></tr>}
            </tbody>
          </table>
        </div>

        {selected ? (
          <ShipmentTimeline shipment={shipments.data?.find((s) => s.id === selected) ?? null} />
        ) : (
          <div className="ec-card p-6 text-center text-sm text-ink-muted">Click a tracking number to see the event timeline.</div>
        )}
      </div>
    </div>
  );
}

function ShipmentForm({ editing, onSaved, onCancel }: { editing: Shipment | null; onSaved: () => void; onCancel: () => void }) {
  const [trackingNumber, setTrackingNumber] = useState(editing?.tracking_number ?? '');
  const [carrier, setCarrier] = useState(editing?.carrier ?? '');
  const [status, setStatus] = useState(editing?.status ?? 'pending');
  const [direction, setDirection] = useState(editing?.direction ?? 'inbound');
  const [shipDate, setShipDate] = useState(editing?.ship_date ?? '');
  const [expectedDate, setExpectedDate] = useState(editing?.expected_date ?? '');
  const [origin, setOrigin] = useState(editing?.origin ?? '');
  const [destination, setDestination] = useState(editing?.destination ?? '');
  const [notes, setNotes] = useState(editing?.notes ?? '');

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        tracking_number: trackingNumber, carrier: carrier || null,
        status, direction, ship_date: shipDate || null, expected_date: expectedDate || null,
        delivered_date: editing?.delivered_date ?? null,
        purchase_order_id: editing?.purchase_order_id ?? null,
        origin: origin || null, destination: destination || null, notes,
      };
      if (editing) return (await api.patch(`/inventory/shipments/${editing.id}`, body)).data;
      return (await api.post('/inventory/shipments', body)).data;
    },
    onSuccess: () => { toast.success('Saved'); onSaved(); },
    onError: () => toast.error('Save failed'),
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? 'Edit shipment' : 'New shipment'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div className="md:col-span-2"><label className="ec-label">Tracking number</label><input className="ec-input font-mono" value={trackingNumber} onChange={(e) => setTrackingNumber(e.target.value)} /></div>
        <div><label className="ec-label">Carrier</label><input className="ec-input" value={carrier ?? ''} onChange={(e) => setCarrier(e.target.value)} placeholder="UPS, FedEx, DHL…" /></div>
        <div><label className="ec-label">Status</label>
          <select className="ec-input" value={status} onChange={(e) => setStatus(e.target.value)}>
            {SHIPMENT_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Direction</label>
          <select className="ec-input" value={direction} onChange={(e) => setDirection(e.target.value)}>
            <option value="inbound">Inbound</option>
            <option value="outbound">Outbound</option>
          </select>
        </div>
        <div><label className="ec-label">Ship date</label><input type="date" className="ec-input" value={shipDate ?? ''} onChange={(e) => setShipDate(e.target.value)} /></div>
        <div><label className="ec-label">Expected date</label><input type="date" className="ec-input" value={expectedDate ?? ''} onChange={(e) => setExpectedDate(e.target.value)} /></div>
        <div><label className="ec-label">Origin</label><input className="ec-input" value={origin ?? ''} onChange={(e) => setOrigin(e.target.value)} /></div>
        <div><label className="ec-label">Destination</label><input className="ec-input" value={destination ?? ''} onChange={(e) => setDestination(e.target.value)} /></div>
        <div className="md:col-span-3"><label className="ec-label">Notes</label><textarea className="ec-input" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!trackingNumber || save.isPending} onClick={() => save.mutate()}>{editing ? 'Save' : 'Create'}</button>
      </div>
    </div>
  );
}

function ShipmentTimeline({ shipment }: { shipment: Shipment | null }) {
  const qc = useQueryClient();
  const [eventStatus, setEventStatus] = useState('in_transit');
  const [eventLocation, setEventLocation] = useState('');
  const [eventDescription, setEventDescription] = useState('');

  const events = useQuery({
    queryKey: ['inventory', 'shipment-events', shipment?.id],
    queryFn: async () => shipment ? (await api.get<ShipmentEvent[]>(`/inventory/shipments/${shipment.id}/events`)).data : [],
    enabled: !!shipment,
  });

  const addEvent = useMutation({
    mutationFn: async () => {
      if (!shipment) return null;
      return (await api.post(`/inventory/shipments/${shipment.id}/events`, {
        shipment_id: shipment.id,
        timestamp: new Date().toISOString(),
        location: eventLocation || null,
        status: eventStatus,
        description: eventDescription,
      })).data;
    },
    onSuccess: () => {
      setEventLocation(''); setEventDescription('');
      qc.invalidateQueries({ queryKey: ['inventory', 'shipment-events'] });
      qc.invalidateQueries({ queryKey: ['inventory', 'shipments'] });
      toast.success('Event logged');
    },
  });

  if (!shipment) return null;
  return (
    <div className="space-y-3">
      <div className="ec-card p-4">
        <div className="flex items-center gap-2">
          <Truck size={16} className="text-brand-600" />
          <h3 className="font-semibold">{shipment.tracking_number}</h3>
        </div>
        <p className="mt-1 text-xs text-ink-muted">{shipment.carrier} · {shipment.direction}</p>
        <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
          <div><p className="text-ink-muted">Origin</p><p>{shipment.origin ?? '—'}</p></div>
          <div><p className="text-ink-muted">Destination</p><p>{shipment.destination ?? '—'}</p></div>
        </div>
      </div>

      <div className="ec-card p-4">
        <p className="mb-2 text-sm font-semibold">Add tracking event</p>
        <div className="grid gap-2 md:grid-cols-[140px_1fr_auto]">
          <select className="ec-input" value={eventStatus} onChange={(e) => setEventStatus(e.target.value)}>
            {SHIPMENT_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            <option value="picked_up">picked up</option>
            <option value="customs">customs</option>
            <option value="out_for_delivery">out for delivery</option>
          </select>
          <input className="ec-input" placeholder="Location (city, country)" value={eventLocation} onChange={(e) => setEventLocation(e.target.value)} />
          <button className="ec-btn-primary" disabled={addEvent.isPending} onClick={() => addEvent.mutate()}>Log</button>
        </div>
        <input className="ec-input mt-2" placeholder="Description (optional)" value={eventDescription} onChange={(e) => setEventDescription(e.target.value)} />
      </div>

      <div className="ec-card overflow-hidden">
        <div className="border-b border-border bg-surface-muted px-3 py-2 text-sm font-semibold">Event timeline</div>
        <div className="max-h-96 overflow-y-auto">
          {events.data?.length ? events.data.map((e) => (
            <div key={e.id} className="border-b border-border/60 p-3 last:border-b-0">
              <div className="flex items-start gap-2">
                <MapPin size={14} className="mt-1 shrink-0 text-brand-600" />
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <span className={STATUS_BADGE[e.status] ?? 'ec-badge'}>{e.status}</span>
                    <span className="text-xs text-ink-muted">{formatDateTime(e.timestamp)}</span>
                  </div>
                  {e.location && <p className="mt-1 text-sm">{e.location}</p>}
                  {e.description && <p className="text-xs text-ink-muted">{e.description}</p>}
                </div>
              </div>
            </div>
          )) : <p className="p-4 text-center text-xs text-ink-muted">No events yet.</p>}
        </div>
      </div>
    </div>
  );
}
