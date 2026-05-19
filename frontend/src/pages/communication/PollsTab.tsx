import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Check, BarChart3 } from 'lucide-react';
import { api } from '../../lib/api';

type PollOption = { id: string; label: string; votes: number };
type Poll = { id: string; question: string; multi_choice: boolean; closes_at: string | null; options: PollOption[]; total_votes: number };

export function PollsTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const polls = useQuery({
    queryKey: ['comm', 'polls'],
    queryFn: async () => (await api.get<Poll[]>('/communication/polls')).data,
  });

  const vote = useMutation({
    mutationFn: async (optionIds: string[]) => (await api.post('/communication/polls/vote', { option_ids: optionIds })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['comm', 'polls'] }),
  });

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between">
        <div>
          <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><BarChart3 size={14} />Polls</p>
          <p className="text-sm text-ink-muted">{polls.data?.length ?? 0} polls</p>
        </div>
        <button className="ec-btn-primary" onClick={() => setShow((v) => !v)}><Plus size={14} />{show ? 'Close' : 'New poll'}</button>
      </div>

      {show && <NewPoll onSaved={() => { setShow(false); qc.invalidateQueries({ queryKey: ['comm', 'polls'] }); }} />}

      <div className="space-y-3">
        {polls.data?.length ? polls.data.map((p) => (
          <PollCard key={p.id} poll={p} onVote={(ids) => vote.mutate(ids)} />
        )) : <p className="text-sm text-ink-muted">No polls.</p>}
      </div>
    </div>
  );
}

function PollCard({ poll, onVote }: { poll: Poll; onVote: (ids: string[]) => void }) {
  const [picked, setPicked] = useState<Set<string>>(new Set());
  function toggle(id: string) {
    setPicked((s) => {
      const next = new Set(s);
      if (poll.multi_choice) {
        if (next.has(id)) next.delete(id); else next.add(id);
      } else {
        next.clear(); next.add(id);
      }
      return next;
    });
  }
  return (
    <div className="ec-card p-5">
      <p className="font-semibold">{poll.question}</p>
      <p className="text-xs text-ink-muted">{poll.total_votes} vote(s) · {poll.multi_choice ? 'multi-choice' : 'single choice'}</p>
      <div className="mt-3 space-y-2">
        {poll.options.map((o) => {
          const pct = poll.total_votes ? (o.votes / poll.total_votes) * 100 : 0;
          return (
            <label key={o.id} className="block cursor-pointer">
              <div className="mb-1 flex items-center justify-between text-sm">
                <span>
                  <input type={poll.multi_choice ? 'checkbox' : 'radio'} className="mr-2" checked={picked.has(o.id)} onChange={() => toggle(o.id)} />
                  {o.label}
                </span>
                <span className="text-xs text-ink-muted">{o.votes} ({pct.toFixed(0)}%)</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded bg-surface-muted">
                <div className="h-full bg-brand-500" style={{ width: `${pct}%` }} />
              </div>
            </label>
          );
        })}
      </div>
      <div className="mt-3 flex justify-end">
        <button className="ec-btn-primary" disabled={picked.size === 0} onClick={() => onVote(Array.from(picked))}>
          <Check size={14} />Submit vote
        </button>
      </div>
    </div>
  );
}

function NewPoll({ onSaved }: { onSaved: () => void }) {
  const [question, setQuestion] = useState('');
  const [options, setOptions] = useState<string[]>(['Yes', 'No']);
  const [multi, setMulti] = useState(false);
  const save = useMutation({
    mutationFn: async () => (await api.post('/communication/polls', {
      question, options: options.filter(Boolean), multi_choice: multi, closes_at: null,
    })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 space-y-3">
      <div><label className="ec-label">Question</label><input className="ec-input" value={question} onChange={(e) => setQuestion(e.target.value)} /></div>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={multi} onChange={(e) => setMulti(e.target.checked)} />Allow multiple choices</label>
      <div className="space-y-2">
        {options.map((o, i) => (
          <div key={i} className="flex gap-2">
            <input className="ec-input" value={o} onChange={(e) => setOptions(options.map((x, ix) => ix === i ? e.target.value : x))} />
            <button className="ec-btn-ghost text-rose-600" onClick={() => setOptions(options.filter((_, ix) => ix !== i))}>×</button>
          </div>
        ))}
        <button type="button" className="ec-btn-secondary" onClick={() => setOptions([...options, ''])}>+ Option</button>
      </div>
      <div className="flex justify-end"><button className="ec-btn-primary" disabled={!question || options.length < 2 || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Create poll'}</button></div>
    </div>
  );
}
