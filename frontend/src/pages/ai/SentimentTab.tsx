import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Heart, ThumbsDown, ThumbsUp, Minus } from 'lucide-react';
import { api } from '../../lib/api';

type Result = { label: string; score: number; summary: string };

export function SentimentTab() {
  const [text, setText] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const analyze = useMutation({
    mutationFn: async () => (await api.post<Result>('/ai/sentiment', { text })).data,
    onSuccess: (d) => setResult(d),
  });

  const Icon = result?.label === 'positive' ? ThumbsUp
    : result?.label === 'negative' ? ThumbsDown : Minus;
  const tone = result?.label === 'positive' ? 'text-emerald-500'
    : result?.label === 'negative' ? 'text-rose-500' : 'text-amber-500';

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="ec-card p-5 space-y-3">
        <p className="flex items-center gap-2 text-sm font-semibold"><Heart size={16} /> Customer feedback / review</p>
        <textarea className="ec-input min-h-[200px]" value={text} onChange={(e) => setText(e.target.value)}
                  placeholder="Paste a review, support ticket, or any text to classify." />
        <button className="ec-btn-primary w-full" disabled={!text.trim() || analyze.isPending}
                onClick={() => analyze.mutate()}>
          {analyze.isPending ? 'Analysing…' : 'Analyse sentiment'}
        </button>
      </div>
      <div className="ec-card p-5">
        {result ? (
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <Icon size={32} className={tone} />
              <div>
                <p className={`text-2xl font-semibold capitalize ${tone}`}>{result.label}</p>
                <p className="text-sm text-ink-muted">Confidence {(result.score * 100).toFixed(0)}%</p>
              </div>
            </div>
            <div className="h-2 overflow-hidden rounded bg-surface-muted">
              <div className={`h-full ${result.label === 'positive' ? 'bg-emerald-500' : result.label === 'negative' ? 'bg-rose-500' : 'bg-amber-500'}`}
                   style={{ width: `${result.score * 100}%` }} />
            </div>
            <p className="rounded-lg bg-surface-muted p-3 text-sm">{result.summary}</p>
          </div>
        ) : (
          <p className="text-sm text-ink-muted">Result appears here. The classifier returns positive / neutral / negative + a one-sentence summary.</p>
        )}
      </div>
    </div>
  );
}
