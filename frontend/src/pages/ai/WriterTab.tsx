import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Copy, PenLine } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';

export function WriterTab() {
  const [kind, setKind] = useState('email');
  const [tone, setTone] = useState('professional');
  const [audience, setAudience] = useState('');
  const [length, setLength] = useState<'short' | 'medium' | 'long'>('medium');
  const [bullets, setBullets] = useState('');
  const [text, setText] = useState('');

  const write = useMutation({
    mutationFn: async () => (await api.post('/ai/writer', {
      kind, tone, audience, length, bullet_points: bullets,
    })).data,
    onSuccess: (d) => setText(d.text),
  });

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="ec-card p-5 space-y-3">
        <p className="flex items-center gap-2 text-sm font-semibold"><PenLine size={16} /> Compose</p>
        <div className="grid grid-cols-2 gap-3">
          <div><label className="ec-label">Kind</label>
            <select className="ec-input" value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="email">Email</option>
              <option value="memo">Internal memo</option>
              <option value="announcement">Announcement</option>
              <option value="policy">Policy</option>
              <option value="proposal">Sales proposal</option>
              <option value="report">Report</option>
            </select>
          </div>
          <div><label className="ec-label">Tone</label>
            <select className="ec-input" value={tone} onChange={(e) => setTone(e.target.value)}>
              <option value="professional">Professional</option>
              <option value="friendly">Friendly</option>
              <option value="formal">Formal</option>
              <option value="enthusiastic">Enthusiastic</option>
              <option value="apologetic">Apologetic</option>
            </select>
          </div>
          <div className="col-span-2"><label className="ec-label">Audience (optional)</label>
            <input className="ec-input" value={audience} onChange={(e) => setAudience(e.target.value)}
                   placeholder="e.g. internal engineering team" />
          </div>
          <div className="col-span-2"><label className="ec-label">Length</label>
            <select className="ec-input" value={length} onChange={(e) => setLength(e.target.value as any)}>
              <option value="short">Short (1 paragraph)</option>
              <option value="medium">Medium (2-3 paragraphs)</option>
              <option value="long">Long (4-6 paragraphs)</option>
            </select>
          </div>
        </div>
        <div>
          <label className="ec-label">Bullet points / key facts</label>
          <textarea className="ec-input min-h-[140px]" value={bullets}
                    onChange={(e) => setBullets(e.target.value)}
                    placeholder={"- Q3 revenue beat target by 12%\n- New office opening in Dublin\n- Three open eng roles"} />
        </div>
        <button className="ec-btn-primary w-full" disabled={!bullets.trim() || write.isPending}
                onClick={() => write.mutate()}>
          {write.isPending ? 'Writing…' : 'Generate'}
        </button>
      </div>

      <div className="ec-card p-5 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold">Result</p>
          {text && (
            <button className="ec-btn-ghost" onClick={() => { navigator.clipboard.writeText(text); toast.success('Copied'); }}>
              <Copy size={14} /> Copy
            </button>
          )}
        </div>
        {text ? (
          <pre className="whitespace-pre-wrap rounded-lg bg-surface-muted p-3 font-sans text-sm">{text}</pre>
        ) : (
          <p className="text-sm text-ink-muted">Output appears here.</p>
        )}
      </div>
    </div>
  );
}
