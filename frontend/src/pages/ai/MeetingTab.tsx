import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { FileText, CheckCircle2 } from 'lucide-react';
import { api } from '../../lib/api';

type Result = { summary: string; key_decisions: string[]; action_items: { owner: string; task: string; due: string }[] };

export function MeetingTab() {
  const [transcript, setTranscript] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const summarise = useMutation({
    mutationFn: async () => (await api.post<Result>('/ai/meeting/summarise', { transcript })).data,
    onSuccess: setResult,
  });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="ec-card p-5 space-y-3">
        <p className="flex items-center gap-2 text-sm font-semibold"><FileText size={16} /> Meeting transcript</p>
        <textarea className="ec-input min-h-[280px]" value={transcript} onChange={(e) => setTranscript(e.target.value)}
                  placeholder="Paste the raw transcript or notes from your meeting." />
        <button className="ec-btn-primary w-full" disabled={transcript.trim().length < 20 || summarise.isPending}
                onClick={() => summarise.mutate()}>
          {summarise.isPending ? 'Summarising…' : 'Summarise'}
        </button>
      </div>
      <div className="space-y-3">
        {result ? (
          <>
            <div className="ec-card p-4">
              <p className="text-xs uppercase tracking-wider text-ink-muted">Summary</p>
              <p className="mt-1 text-sm">{result.summary}</p>
            </div>
            {result.key_decisions.length > 0 && (
              <div className="ec-card p-4">
                <p className="mb-2 text-xs uppercase tracking-wider text-ink-muted">Key decisions</p>
                <ul className="list-disc pl-5 space-y-1 text-sm">
                  {result.key_decisions.map((d, i) => <li key={i}>{d}</li>)}
                </ul>
              </div>
            )}
            {result.action_items.length > 0 && (
              <div className="ec-card p-4">
                <p className="mb-2 text-xs uppercase tracking-wider text-ink-muted">Action items</p>
                <ul className="space-y-2 text-sm">
                  {result.action_items.map((a, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <CheckCircle2 size={14} className="mt-1 shrink-0 text-emerald-500" />
                      <span>
                        <strong>{a.owner || 'Unassigned'}</strong>: {a.task}
                        {a.due && <span className="ml-2 text-xs text-ink-muted">(due {a.due})</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        ) : (
          <div className="ec-card grid h-full place-items-center p-6 text-sm text-ink-muted">
            Summary, key decisions, and action items will appear here.
          </div>
        )}
      </div>
    </div>
  );
}
