import { useState } from 'react';
import { Eye, EyeOff, Key, Lock, ShieldCheck, ShieldOff, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { PROVIDER_LABELS } from '../providers';
import { useApiKeys } from '../useApiKeys';
import type { AiProvider } from '../types';

const PLACEHOLDERS: Record<AiProvider, string> = {
  anthropic: 'sk-ant-…  (https://console.anthropic.com/settings/keys)',
  openai: 'sk-…  (https://platform.openai.com/api-keys)',
  ollama: 'http://127.0.0.1:11434  (or leave blank to use local default)',
};

export function ApiKeySettingsPanel() {
  const { keys, status, update, clearAll } = useApiKeys();
  const [reveal, setReveal] = useState<Record<AiProvider, boolean>>({
    anthropic: false, openai: false, ollama: false,
  });
  const [drafts, setDrafts] = useState<Record<AiProvider, string>>({
    anthropic: '', openai: '', ollama: '',
  });

  const save = async (p: AiProvider) => {
    await update(p, drafts[p] || null);
    setDrafts((d) => ({ ...d, [p]: '' }));
    toast.success(drafts[p] ? `${PROVIDER_LABELS[p]} key saved (encrypted)` : `${PROVIDER_LABELS[p]} key cleared`);
  };

  return (
    <div className="space-y-4 p-4 text-sm">
      <header>
        <h3 className="text-lg font-semibold">API Keys & Vault</h3>
        <p className="mt-1 text-xs text-ink-muted">
          Bring your own keys. Stored locally — never sent to any server other than the AI provider you choose.
        </p>
      </header>

      <div className="flex items-center gap-2 rounded-lg border border-border bg-surface-muted p-3 text-xs">
        {status.isDesktop && status.encrypted ? (
          <>
            <ShieldCheck size={14} className="text-emerald-500" />
            <span>Desktop vault active — keys are encrypted at rest using your operating system's secure credential store (Electron <code>safeStorage</code>).</span>
          </>
        ) : status.isDesktop ? (
          <>
            <ShieldOff size={14} className="text-amber-500" />
            <span>Desktop vault is available but OS encryption is not — keys are stored as a 0600 file in your user-data directory.</span>
          </>
        ) : (
          <>
            <Lock size={14} className="text-ink-muted" />
            <span>Web mode — keys are stored in localStorage on this machine only. For maximum protection install the desktop app.</span>
          </>
        )}
      </div>

      <div className="space-y-3">
        {(Object.keys(PROVIDER_LABELS) as AiProvider[]).map((p) => (
          <div key={p} className="rounded-lg border border-border p-3">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Key size={12} className="text-ink-muted" />
                <span className="font-medium">{PROVIDER_LABELS[p]}</span>
                {keys[p] ? (
                  <span className="ec-badge-green">configured</span>
                ) : (
                  <span className="ec-badge-amber">not set</span>
                )}
              </div>
              <button
                className="ec-btn-ghost px-2 py-1 text-[11px]"
                onClick={() => setReveal((r) => ({ ...r, [p]: !r[p] }))}
              >
                {reveal[p] ? <EyeOff size={11} /> : <Eye size={11} />}
                {reveal[p] ? 'Hide current' : 'Show current'}
              </button>
            </div>
            {reveal[p] && (
              <p className="mb-2 break-all rounded bg-surface-muted p-2 font-mono text-[11px]">
                {keys[p] || '(not set)'}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <input
                type="password"
                className="ec-input flex-1 font-mono text-xs"
                placeholder={PLACEHOLDERS[p]}
                value={drafts[p]}
                onChange={(e) => setDrafts((d) => ({ ...d, [p]: e.target.value }))}
              />
              <button className="ec-btn-primary text-xs" onClick={() => save(p)}>Save</button>
              {keys[p] && (
                <button className="ec-btn-danger text-xs" onClick={() => update(p, null).then(() => toast.success(`${PROVIDER_LABELS[p]} key cleared`))}>
                  <Trash2 size={11} /> Clear
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between border-t border-border pt-3">
        <p className="text-xs text-ink-muted">
          When no BYO key is set, the desktop will fall back to the server-configured key (if present) or the local Ollama daemon.
        </p>
        <button className="ec-btn-secondary text-xs" onClick={async () => { await clearAll(); toast.success('All keys cleared'); }}>
          Clear all
        </button>
      </div>
    </div>
  );
}
