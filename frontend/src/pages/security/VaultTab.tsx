import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Copy, Eye, EyeOff, KeyRound, Plus, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';

type Entry = { id: string; title: string; username: string | null; created_at: string };
type Revealed = { id: string; title: string; username: string | null; password: string; notes: string | null };

export function VaultTab() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ['security', 'vault'],
    queryFn: async () => (await api.get<Entry[]>('/security/vault')).data,
  });
  const [revealed, setRevealed] = useState<Record<string, Revealed>>({});
  const [show, setShow] = useState(false);

  const reveal = async (id: string) => {
    if (revealed[id]) {
      setRevealed((r) => { const { [id]: _, ...rest } = r; return rest; });
      return;
    }
    const r = await api.get<Revealed>(`/security/vault/${id}/reveal`);
    setRevealed((curr) => ({ ...curr, [id]: r.data }));
  };

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/security/vault/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['security', 'vault'] }),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-muted">{data?.length ?? 0} entries · encrypted at rest with Fernet/AES-128</p>
        <button className="ec-btn-primary" onClick={() => setShow((v) => !v)}>
          <Plus size={16} /> {show ? 'Close' : 'New entry'}
        </button>
      </div>

      {show && <VaultForm onSaved={() => { setShow(false); qc.invalidateQueries({ queryKey: ['security', 'vault'] }); }} />}

      <table className="ec-table">
        <thead><tr><th>Title</th><th>Username</th><th>Password</th><th></th></tr></thead>
        <tbody>
          {data?.length ? data.map((e) => {
            const r = revealed[e.id];
            return (
              <tr key={e.id}>
                <td className="font-medium"><div className="flex items-center gap-2"><KeyRound size={14} className="text-ink-muted" />{e.title}</div></td>
                <td>{e.username ?? '—'}</td>
                <td className="font-mono text-xs">
                  {r ? (
                    <span className="inline-flex items-center gap-2">
                      <span className="rounded bg-surface-muted px-1.5 py-0.5">{r.password}</span>
                      <button className="ec-btn-ghost" title="Copy" onClick={() => { navigator.clipboard.writeText(r.password); toast.success('Copied'); }}>
                        <Copy size={14} />
                      </button>
                    </span>
                  ) : <span className="text-ink-subtle">••••••••</span>}
                </td>
                <td className="text-right whitespace-nowrap">
                  <button className="ec-btn-ghost" onClick={() => reveal(e.id)}>{r ? <EyeOff size={14} /> : <Eye size={14} />}</button>
                  <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete ' + e.title + '?')) remove.mutate(e.id); }}><Trash2 size={14} /></button>
                </td>
              </tr>
            );
          }) : <tr><td colSpan={4} className="py-8 text-center text-ink-muted">Vault is empty.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function VaultForm({ onSaved }: { onSaved: () => void }) {
  const [title, setTitle] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [notes, setNotes] = useState('');

  const save = useMutation({
    mutationFn: async () => (await api.post('/security/vault', { title, username, password, notes })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 grid gap-3 md:grid-cols-2">
      <div><label className="ec-label">Title</label><input className="ec-input" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
      <div><label className="ec-label">Username</label><input className="ec-input" value={username} onChange={(e) => setUsername(e.target.value)} /></div>
      <div className="md:col-span-2"><label className="ec-label">Password</label>
        <input type="password" className="ec-input" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
      <div className="md:col-span-2"><label className="ec-label">Notes</label>
        <textarea className="ec-input" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
      <div className="md:col-span-2 flex justify-end">
        <button className="ec-btn-primary" disabled={!title || !password || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save'}</button>
      </div>
    </div>
  );
}
