import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Briefcase } from 'lucide-react';
import { api } from '../../lib/api';

type Opening = { id: string; title: string; department: string | null; status: string; description: string };
type Candidate = { id: string; job_opening_id: string | null; full_name: string; email: string | null; stage: string; rating: string };

const STAGES = ['applied', 'screening', 'interview', 'offer', 'hired', 'rejected'];
const STAGE_BADGE: Record<string, string> = {
  applied: 'ec-badge-blue', screening: 'ec-badge-blue', interview: 'ec-badge-amber',
  offer: 'ec-badge-amber', hired: 'ec-badge-green', rejected: 'ec-badge-rose',
};

export function RecruitmentTab() {
  const qc = useQueryClient();
  const [showOp, setShowOp] = useState(false);
  const [showCand, setShowCand] = useState(false);
  const [selectedOp, setSelectedOp] = useState<string | null>(null);

  const openings = useQuery({
    queryKey: ['hr', 'openings'],
    queryFn: async () => (await api.get<Opening[]>('/hr/openings')).data,
  });
  const candidates = useQuery({
    queryKey: ['hr', 'candidates', selectedOp],
    queryFn: async () => (await api.get<Candidate[]>('/hr/candidates', {
      params: selectedOp ? { job_opening_id: selectedOp } : {},
    })).data,
  });

  const updateOpening = useMutation({
    mutationFn: async (o: Opening) => (await api.patch(`/hr/openings/${o.id}`, {
      title: o.title, department: o.department, status: o.status, description: o.description,
    })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hr', 'openings'] }),
  });
  const removeOpening = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/hr/openings/${id}`)).data,
    onSuccess: () => { if (selectedOp) setSelectedOp(null); qc.invalidateQueries({ queryKey: ['hr', 'openings'] }); },
  });
  const updateCandidate = useMutation({
    mutationFn: async (c: Candidate) => (await api.patch(`/hr/candidates/${c.id}`, {
      job_opening_id: c.job_opening_id, full_name: c.full_name, email: c.email, stage: c.stage, rating: parseFloat(c.rating),
    })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hr', 'candidates'] }),
  });
  const removeCandidate = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/hr/candidates/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hr', 'candidates'] }),
  });

  const byStage = (candidates.data ?? []).reduce<Record<string, Candidate[]>>((acc, c) => {
    (acc[c.stage] ??= []).push(c); return acc;
  }, {});

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Recruitment</p>
          <p className="text-sm text-ink-muted">{openings.data?.length ?? 0} openings · {candidates.data?.length ?? 0} candidates</p>
        </div>
        <div className="flex gap-2">
          <button className="ec-btn-secondary" onClick={() => setShowOp((v) => !v)}><Briefcase size={16} />{showOp ? 'Close' : 'New opening'}</button>
          <button className="ec-btn-primary" onClick={() => setShowCand((v) => !v)}><Plus size={16} />{showCand ? 'Close' : 'New candidate'}</button>
        </div>
      </div>

      {showOp && <OpeningForm onSaved={() => { setShowOp(false); qc.invalidateQueries({ queryKey: ['hr', 'openings'] }); }} />}
      {showCand && <CandidateForm openings={openings.data ?? []} onSaved={() => { setShowCand(false); qc.invalidateQueries({ queryKey: ['hr', 'candidates'] }); }} />}

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <div className="ec-card p-3">
          <p className="px-2 pb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">Openings</p>
          <ul className="space-y-1">
            <li>
              <button onClick={() => setSelectedOp(null)}
                      className={`flex w-full justify-between rounded-md px-3 py-2 text-left text-sm ${selectedOp === null ? 'bg-brand-600 text-white' : 'hover:bg-surface-muted'}`}>
                All openings
              </button>
            </li>
            {openings.data?.map((o) => (
              <li key={o.id}>
                <button onClick={() => setSelectedOp(o.id)}
                        className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm ${selectedOp === o.id ? 'bg-brand-600 text-white' : 'hover:bg-surface-muted'}`}>
                  <span><span className="font-medium">{o.title}</span> <span className={`ml-1 text-xs ${selectedOp === o.id ? 'text-white/70' : 'text-ink-muted'}`}>{o.department ?? ''}</span></span>
                  <span className={`text-[10px] uppercase ${o.status === 'open' ? 'text-emerald-500' : 'text-ink-muted'}`}>{o.status}</span>
                </button>
              </li>
            ))}
          </ul>
          {selectedOp && (() => {
            const op = openings.data?.find((o) => o.id === selectedOp);
            if (!op) return null;
            return (
              <div className="mt-3 rounded-lg border border-border bg-surface-muted p-3 text-xs">
                <p className="font-medium">{op.title}</p>
                <p className="mt-1 text-ink-muted">{op.description || 'No description.'}</p>
                <div className="mt-2 flex justify-end gap-1">
                  <select className="ec-input !py-1 !w-28" value={op.status} onChange={(e) => updateOpening.mutate({ ...op, status: e.target.value })}>
                    <option value="open">open</option>
                    <option value="paused">paused</option>
                    <option value="closed">closed</option>
                  </select>
                  <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete opening?')) removeOpening.mutate(op.id); }}><Trash2 size={14} /></button>
                </div>
              </div>
            );
          })()}
        </div>

        <div>
          <p className="mb-2 text-sm font-semibold">Pipeline {selectedOp ? `for ${openings.data?.find((o) => o.id === selectedOp)?.title}` : '(all openings)'}</p>
          <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-6">
            {STAGES.map((stage) => (
              <div key={stage} className="rounded-xl border border-border bg-surface-muted p-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className={`ec-badge ${STAGE_BADGE[stage]}`}>{stage}</span>
                  <span className="text-xs text-ink-muted">{(byStage[stage] ?? []).length}</span>
                </div>
                <div className="space-y-2">
                  {(byStage[stage] ?? []).map((c) => (
                    <div key={c.id} className="rounded-md bg-surface-elevated p-2 text-xs shadow-sm">
                      <p className="font-medium">{c.full_name}</p>
                      <p className="text-ink-muted">{c.email ?? '—'}</p>
                      <div className="mt-1 flex items-center gap-1">
                        <select className="ec-input !py-0.5 !text-xs" value={c.stage}
                                onChange={(e) => updateCandidate.mutate({ ...c, stage: e.target.value })}>
                          {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
                        </select>
                        <button className="ec-btn-ghost text-rose-600 !p-1" onClick={() => { if (confirm('Delete candidate?')) removeCandidate.mutate(c.id); }}><Trash2 size={12} /></button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function OpeningForm({ onSaved }: { onSaved: () => void }) {
  const [title, setTitle] = useState('');
  const [department, setDepartment] = useState('Engineering');
  const [description, setDescription] = useState('');
  const save = useMutation({
    mutationFn: async () => (await api.post('/hr/openings', { title, department, description })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 grid gap-3 md:grid-cols-3">
      <div className="md:col-span-2"><label className="ec-label">Title</label><input className="ec-input" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
      <div><label className="ec-label">Department</label><input className="ec-input" value={department} onChange={(e) => setDepartment(e.target.value)} /></div>
      <div className="md:col-span-3"><label className="ec-label">Description</label><textarea rows={2} className="ec-input" value={description} onChange={(e) => setDescription(e.target.value)} /></div>
      <div className="md:col-span-3 flex justify-end"><button className="ec-btn-primary" disabled={!title || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save'}</button></div>
    </div>
  );
}

function CandidateForm({ openings, onSaved }: { openings: Opening[]; onSaved: () => void }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [opId, setOpId] = useState(openings[0]?.id ?? '');
  const [stage, setStage] = useState('applied');
  const save = useMutation({
    mutationFn: async () => (await api.post('/hr/candidates', {
      job_opening_id: opId || null, full_name: name, email: email || null, stage, rating: 0,
    })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 grid gap-3 md:grid-cols-5">
      <div><label className="ec-label">Name</label><input className="ec-input" value={name} onChange={(e) => setName(e.target.value)} /></div>
      <div><label className="ec-label">Email</label><input className="ec-input" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
      <div><label className="ec-label">Opening</label>
        <select className="ec-input" value={opId} onChange={(e) => setOpId(e.target.value)}>
          <option value="">—</option>
          {openings.map((o) => <option key={o.id} value={o.id}>{o.title}</option>)}
        </select>
      </div>
      <div><label className="ec-label">Stage</label>
        <select className="ec-input" value={stage} onChange={(e) => setStage(e.target.value)}>
          {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <div className="flex items-end"><button className="ec-btn-primary w-full" disabled={!name || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save'}</button></div>
    </div>
  );
}
