import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Save, ShieldCheck, Trash2 } from 'lucide-react';
import { samlMetadataUrl, ssoApi, type SSOConfigIn, type SSOProviderType } from '../../lib/sso';
import { useAuthStore } from '../../store/auth';
import { PermissionDenied } from './OrgLayout';

type Mode = 'none' | SSOProviderType;

const EMPTY: SSOConfigIn = {
  provider_type: 'oidc',
  is_enabled: true,
  email_attribute: 'email',
  name_attribute: 'name',
  auto_provision_users: false,
  default_role_for_new_users: 'employee',
};

export function SSOTab() {
  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasRole('Admin'));
  const tenant = useAuthStore((s) => s.tenant);

  const cfgQ = useQuery({
    queryKey: ['sso', 'config'],
    queryFn: () => ssoApi.getConfig().catch(() => null),
    enabled: isAdmin,
  });

  const [mode, setMode] = useState<Mode>('none');
  const [form, setForm] = useState<SSOConfigIn>(EMPTY);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (cfgQ.data && !hydrated) {
      setMode(cfgQ.data.provider_type);
      setForm({
        provider_type: cfgQ.data.provider_type,
        is_enabled: cfgQ.data.is_enabled,
        issuer_url: cfgQ.data.issuer_url,
        client_id: cfgQ.data.client_id,
        client_secret: '',
        idp_metadata_url: cfgQ.data.idp_metadata_url,
        idp_entity_id: cfgQ.data.idp_entity_id,
        idp_sso_url: cfgQ.data.idp_sso_url,
        idp_x509_cert: cfgQ.data.idp_x509_cert,
        sp_entity_id: cfgQ.data.sp_entity_id,
        email_attribute: cfgQ.data.email_attribute,
        name_attribute: cfgQ.data.name_attribute,
        auto_provision_users: cfgQ.data.auto_provision_users,
        default_role_for_new_users: cfgQ.data.default_role_for_new_users,
      });
      setHydrated(true);
    } else if (cfgQ.data === null && !hydrated) {
      setHydrated(true);
    }
  }, [cfgQ.data, hydrated]);

  const save = useMutation({
    mutationFn: () => ssoApi.upsertConfig({ ...form, provider_type: mode === 'none' ? 'oidc' : mode }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sso', 'config'] });
      toast.success('SSO config saved');
      setForm((f) => ({ ...f, client_secret: '' }));
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Could not save'),
  });

  const remove = useMutation({
    mutationFn: () => ssoApi.deleteConfig(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sso', 'config'] });
      setMode('none');
      setForm(EMPTY);
      toast.success('SSO config removed');
    },
  });

  if (!isAdmin) return <PermissionDenied what="configure SSO" />;
  if (cfgQ.isLoading || !hydrated) return <p className="text-sm text-ink-muted">Loading SSO…</p>;

  return (
    <div className="space-y-4">
      <div className="ec-card p-5 space-y-4">
        <header>
          <h2 className="text-lg font-semibold flex items-center gap-2"><ShieldCheck size={18} /> Single Sign-On</h2>
          <p className="text-sm text-ink-muted">Let users sign in with your identity provider.</p>
        </header>

        <div>
          <label className="ec-label">Provider</label>
          <div className="grid gap-2 sm:grid-cols-3">
            {(['none', 'oidc', 'saml'] as Mode[]).map((m) => (
              <label
                key={m}
                className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
                  mode === m ? 'border-brand-600 bg-brand-600/10' : 'border-border bg-surface-muted/30'
                }`}
              >
                <input
                  type="radio"
                  name="ssoMode"
                  checked={mode === m}
                  onChange={() => setMode(m)}
                  data-testid={`sso-mode-${m}`}
                />
                <span className="capitalize">{m === 'none' ? 'No SSO' : m.toUpperCase()}</span>
              </label>
            ))}
          </div>
        </div>

        {mode === 'oidc' ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="ec-label" htmlFor="oidc-preset">Preset</label>
              <select
                id="oidc-preset"
                className="ec-input"
                value={form.preset ?? 'custom'}
                onChange={(e) => setForm((f) => ({ ...f, preset: e.target.value as any }))}
              >
                <option value="custom">Custom</option>
                <option value="google">Google</option>
                <option value="microsoft">Microsoft</option>
                <option value="okta">Okta</option>
              </select>
            </div>
            <div>
              <label className="ec-label" htmlFor="oidc-issuer">Issuer URL</label>
              <input
                id="oidc-issuer"
                className="ec-input"
                value={form.issuer_url ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, issuer_url: e.target.value }))}
                data-testid="oidc-issuer"
              />
            </div>
            <div>
              <label className="ec-label" htmlFor="oidc-cid">Client ID</label>
              <input
                id="oidc-cid"
                className="ec-input"
                value={form.client_id ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, client_id: e.target.value }))}
                data-testid="oidc-client-id"
              />
            </div>
            <div>
              <label className="ec-label" htmlFor="oidc-cs">Client secret</label>
              <input
                id="oidc-cs"
                className="ec-input"
                type="password"
                placeholder={cfgQ.data?.has_client_secret ? '••••••• (saved)' : ''}
                value={form.client_secret ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, client_secret: e.target.value }))}
                data-testid="oidc-client-secret"
              />
            </div>
          </div>
        ) : null}

        {mode === 'saml' ? (
          <div className="grid gap-4">
            <div>
              <label className="ec-label" htmlFor="saml-metadata">IdP metadata URL</label>
              <input
                id="saml-metadata"
                className="ec-input"
                value={form.idp_metadata_url ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, idp_metadata_url: e.target.value }))}
                data-testid="saml-metadata"
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="ec-label" htmlFor="saml-entity">IdP entity ID</label>
                <input
                  id="saml-entity"
                  className="ec-input"
                  value={form.idp_entity_id ?? ''}
                  onChange={(e) => setForm((f) => ({ ...f, idp_entity_id: e.target.value }))}
                />
              </div>
              <div>
                <label className="ec-label" htmlFor="saml-sso">IdP SSO URL</label>
                <input
                  id="saml-sso"
                  className="ec-input"
                  value={form.idp_sso_url ?? ''}
                  onChange={(e) => setForm((f) => ({ ...f, idp_sso_url: e.target.value }))}
                />
              </div>
            </div>
            <div>
              <label className="ec-label" htmlFor="saml-cert">IdP x509 cert (PEM)</label>
              <textarea
                id="saml-cert"
                className="ec-input min-h-[120px] font-mono text-xs"
                value={form.idp_x509_cert ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, idp_x509_cert: e.target.value }))}
              />
            </div>
            {tenant ? (
              <p className="text-xs text-ink-subtle">
                SP metadata:{' '}
                <a className="text-brand-600 hover:underline" href={samlMetadataUrl(tenant.slug)} target="_blank" rel="noreferrer">
                  {samlMetadataUrl(tenant.slug)}
                </a>
              </p>
            ) : null}
          </div>
        ) : null}

        {mode !== 'none' ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="ec-label" htmlFor="email-attr">Email attribute</label>
              <input
                id="email-attr"
                className="ec-input"
                value={form.email_attribute ?? 'email'}
                onChange={(e) => setForm((f) => ({ ...f, email_attribute: e.target.value }))}
              />
            </div>
            <div>
              <label className="ec-label" htmlFor="name-attr">Name attribute</label>
              <input
                id="name-attr"
                className="ec-input"
                value={form.name_attribute ?? 'name'}
                onChange={(e) => setForm((f) => ({ ...f, name_attribute: e.target.value }))}
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={!!form.auto_provision_users}
                onChange={(e) => setForm((f) => ({ ...f, auto_provision_users: e.target.checked }))}
                data-testid="sso-autoprov"
              />
              Auto-provision new users on first sign-in
            </label>
          </div>
        ) : null}

        {mode !== 'none' && tenant ? (
          <div className="rounded-lg bg-surface-muted/40 p-3 text-xs text-ink-muted">
            Test login URL:{' '}
            <a
              className="font-mono text-brand-600 hover:underline"
              href={`#/login?slug=${tenant.slug}`}
            >
              {`${window.location.origin}/#/login`}
            </a>
            {' '}— the public sign-in page will surface a &ldquo;Sign in with SSO&rdquo; option for this tenant once enabled.
          </div>
        ) : null}

        <div className="flex justify-end gap-2">
          {cfgQ.data ? (
            <button
              className="ec-btn-secondary text-rose-600"
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
              data-testid="sso-delete"
            >
              <Trash2 size={16} /> Remove SSO
            </button>
          ) : null}
          {mode !== 'none' ? (
            <button
              className="ec-btn-primary"
              onClick={() => save.mutate()}
              disabled={save.isPending}
              data-testid="sso-save"
            >
              <Save size={16} /> {save.isPending ? 'Saving…' : 'Save SSO config'}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
