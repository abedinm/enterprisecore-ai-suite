import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Key, Lock, RefreshCw, X } from 'lucide-react';
import { encryptionApi, type ByokIn } from '../../lib/security_policies';
import { useAuthStore } from '../../store/auth';
import { formatDateTime } from '../../lib/utils';
import { PermissionDenied } from './OrgLayout';

const PROVIDER_LABELS: Record<ByokIn['kms_provider'], string> = {
  server: 'Server-managed (default)',
  aws_kms: 'AWS KMS',
  gcp_kms: 'Google Cloud KMS',
  azure_kv: 'Azure Key Vault',
  hcv_transit: 'HashiCorp Vault Transit',
};

const PROVIDER_HINT: Record<ByokIn['kms_provider'], string> = {
  server: 'No external KMS — keys stay inside EnterpriseCore.',
  aws_kms: 'Key ARN, e.g. arn:aws:kms:us-east-1:123:key/abc',
  gcp_kms: 'Resource name, e.g. projects/p/locations/us/keyRings/r/cryptoKeys/k',
  azure_kv: 'Key identifier URL, e.g. https://vault.vault.azure.net/keys/name/version',
  hcv_transit: 'Mount path/key, e.g. transit/keys/my-key',
};

export function EncryptionTab() {
  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasRole('Admin'));
  const keyQ = useQuery({ queryKey: ['encryption', 'key'], queryFn: () => encryptionApi.current(), enabled: isAdmin });

  const [rotateConfirmOpen, setRotateConfirmOpen] = useState(false);
  const [byokOpen, setByokOpen] = useState(false);
  const [provider, setProvider] = useState<ByokIn['kms_provider']>('server');
  const [keyRef, setKeyRef] = useState('');

  const rotate = useMutation({
    mutationFn: () => encryptionApi.rotate(),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['encryption'] });
      setRotateConfirmOpen(false);
      toast.success(`Rotated — now on v${data.new_key_version}`);
    },
    onError: () => toast.error('Could not rotate key'),
  });

  const byok = useMutation({
    mutationFn: () => encryptionApi.byok({ kms_provider: provider, kms_key_ref: keyRef }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['encryption'] });
      setByokOpen(false);
      toast.success('BYOK configured');
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Could not configure BYOK'),
  });

  if (!isAdmin) return <PermissionDenied what="manage encryption keys" />;

  return (
    <div className="space-y-4">
      <div className="ec-card p-5 space-y-4">
        <header>
          <h2 className="text-lg font-semibold flex items-center gap-2"><Lock size={18} /> Encryption</h2>
          <p className="text-sm text-ink-muted">Field-level encryption protects sensitive data at rest.</p>
        </header>

        {keyQ.isLoading ? (
          <p className="text-sm text-ink-muted">Loading…</p>
        ) : keyQ.data ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <Stat label="Key version" value={`v${keyQ.data.key_version}`} />
            <Stat label="KMS provider" value={PROVIDER_LABELS[keyQ.data.kms_provider as ByokIn['kms_provider']] ?? keyQ.data.kms_provider} />
            <Stat label="Activated" value={formatDateTime(keyQ.data.activated_at)} />
            <Stat label="Last rotated" value={keyQ.data.rotated_at ? formatDateTime(keyQ.data.rotated_at) : 'Never'} />
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <button className="ec-btn-secondary" onClick={() => setRotateConfirmOpen(true)} data-testid="rotate-open">
            <RefreshCw size={16} /> Rotate key
          </button>
          <button className="ec-btn-secondary" onClick={() => setByokOpen(true)} data-testid="byok-open">
            <Key size={16} /> Switch to BYOK
          </button>
        </div>
      </div>

      {rotateConfirmOpen ? (
        <ConfirmDialog
          title="Rotate encryption key"
          body="A new key version is generated and existing data is re-encrypted in the background. A brief delay may occur during re-encryption."
          onCancel={() => setRotateConfirmOpen(false)}
          onConfirm={() => rotate.mutate()}
          confirmText="Rotate now"
          loading={rotate.isPending}
        />
      ) : null}

      {byokOpen ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-ink/40 backdrop-blur-sm p-4">
          <div className="ec-card w-full max-w-md p-5 relative">
            <button
              className="absolute right-2 top-2 rounded-md p-1.5 text-ink-muted hover:bg-surface-muted"
              onClick={() => setByokOpen(false)}
              aria-label="Close"
            >
              <X size={16} />
            </button>
            <h3 className="text-lg font-semibold">Bring your own key</h3>
            <div className="mt-4 space-y-3">
              <div>
                <label className="ec-label" htmlFor="byok-provider">Provider</label>
                <select
                  id="byok-provider"
                  className="ec-input"
                  value={provider}
                  onChange={(e) => setProvider(e.target.value as ByokIn['kms_provider'])}
                  data-testid="byok-provider"
                >
                  {Object.entries(PROVIDER_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="ec-label" htmlFor="byok-key">Key reference</label>
                <input
                  id="byok-key"
                  className="ec-input font-mono text-xs"
                  value={keyRef}
                  onChange={(e) => setKeyRef(e.target.value)}
                  data-testid="byok-key-ref"
                />
                <p className="mt-1 text-[11px] text-ink-subtle">{PROVIDER_HINT[provider]}</p>
              </div>
              <button
                className="ec-btn-primary w-full"
                onClick={() => byok.mutate()}
                disabled={byok.isPending || !keyRef}
              >
                Configure BYOK
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wider text-ink-subtle">{label}</p>
      <p className="mt-1 font-semibold">{value}</p>
    </div>
  );
}

function ConfirmDialog({
  title, body, confirmText, onConfirm, onCancel, loading,
}: { title: string; body: string; confirmText: string; onConfirm: () => void; onCancel: () => void; loading: boolean }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink/40 backdrop-blur-sm p-4">
      <div className="ec-card w-full max-w-md p-5">
        <h3 className="text-lg font-semibold">{title}</h3>
        <p className="mt-2 text-sm text-ink-muted">{body}</p>
        <div className="mt-4 flex justify-end gap-2">
          <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
          <button className="ec-btn-primary" onClick={onConfirm} disabled={loading} data-testid="confirm-rotate">
            {loading ? 'Working…' : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
