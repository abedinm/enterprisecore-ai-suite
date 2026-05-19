import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Bot, Plus, Trash2 } from 'lucide-react';
import { api } from '../../lib/api';

type Chatbot = {
  id: string; name: string; description: string | null; provider: string;
  model: string | null; temperature: string; is_active: boolean;
  public_token: string | null;
};

export function ChatbotsTab() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ['ai', 'chatbots'],
    queryFn: async () => (await api.get<Chatbot[]>('/ai/chatbots')).data,
  });
  const [show, setShow] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [systemPrompt, setSystemPrompt] = useState(
    'You are a helpful customer-support assistant for Your Company. Answer concisely and only from the information provided.',
  );
  const [welcome, setWelcome] = useState('Hi! How can I help you today?');
  const [provider, setProvider] = useState('anthropic');

  const save = useMutation({
    mutationFn: async () => (await api.post('/ai/chatbots', {
      name, description, system_prompt: systemPrompt,
      welcome_message: welcome, provider, temperature: 0.7, is_active: true,
    })).data,
    onSuccess: () => { setShow(false); setName(''); qc.invalidateQueries({ queryKey: ['ai', 'chatbots'] }); },
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-muted">{data?.length ?? 0} chatbots</p>
        <button className="ec-btn-primary" onClick={() => setShow((v) => !v)}><Plus size={14} /> {show ? 'Close' : 'New chatbot'}</button>
      </div>
      {show && (
        <div className="rounded-xl border border-border bg-surface-muted p-4 space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            <div><label className="ec-label">Name</label><input className="ec-input" value={name} onChange={(e) => setName(e.target.value)} /></div>
            <div><label className="ec-label">Provider</label>
              <select className="ec-input" value={provider} onChange={(e) => setProvider(e.target.value)}>
                <option value="anthropic">Anthropic</option>
                <option value="openai">OpenAI</option>
                <option value="ollama">Ollama (local)</option>
              </select>
            </div>
            <div className="md:col-span-2"><label className="ec-label">Description</label>
              <input className="ec-input" value={description} onChange={(e) => setDescription(e.target.value)} /></div>
            <div className="md:col-span-2"><label className="ec-label">System prompt</label>
              <textarea className="ec-input min-h-[120px]" value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} /></div>
            <div className="md:col-span-2"><label className="ec-label">Welcome message</label>
              <input className="ec-input" value={welcome} onChange={(e) => setWelcome(e.target.value)} /></div>
          </div>
          <div className="flex justify-end">
            <button className="ec-btn-primary" disabled={!name || save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? 'Saving…' : 'Save chatbot'}
            </button>
          </div>
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        {data?.length ? data.map((b) => (
          <div key={b.id} className="ec-card p-4 space-y-1">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2"><Bot size={16} /><p className="font-medium">{b.name}</p></div>
              <span className="ec-badge ec-badge-blue">{b.provider}</span>
            </div>
            {b.description && <p className="text-sm text-ink-muted">{b.description}</p>}
            {b.public_token && (
              <p className="mt-2 text-xs">
                Embed URL: <code className="bg-surface-muted rounded px-1 py-0.5">/chat/{b.public_token}</code>
              </p>
            )}
          </div>
        )) : <p className="text-sm text-ink-muted">No chatbots yet.</p>}
      </div>
    </div>
  );
}
