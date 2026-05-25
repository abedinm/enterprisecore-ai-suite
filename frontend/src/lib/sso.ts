import { api, API_BASE } from './api';

/* -------------------------------------------------------------------------- */
/*  SSO config — mirrors app/schemas/sso.py                                   */
/* -------------------------------------------------------------------------- */

export type SSOProviderType = 'oidc' | 'saml';
export type SSOPreset = 'google' | 'microsoft' | 'okta' | 'custom';

export type SSOConfigIn = {
  provider_type: SSOProviderType;
  is_enabled?: boolean;
  issuer_url?: string | null;
  client_id?: string | null;
  client_secret?: string | null;
  preset?: SSOPreset | null;
  idp_metadata_url?: string | null;
  idp_metadata_xml?: string | null;
  idp_entity_id?: string | null;
  idp_sso_url?: string | null;
  idp_x509_cert?: string | null;
  sp_entity_id?: string | null;
  email_attribute?: string;
  name_attribute?: string;
  groups_attribute?: string | null;
  auto_provision_users?: boolean;
  default_role_for_new_users?: string;
};

export type SSOConfigOut = {
  id: string;
  tenant_id: string;
  provider_type: SSOProviderType;
  is_enabled: boolean;
  issuer_url: string | null;
  client_id: string | null;
  has_client_secret: boolean;
  idp_metadata_url: string | null;
  idp_entity_id: string | null;
  idp_sso_url: string | null;
  idp_x509_cert: string | null;
  sp_entity_id: string | null;
  has_idp_metadata_xml: boolean;
  email_attribute: string;
  name_attribute: string;
  groups_attribute: string | null;
  auto_provision_users: boolean;
  default_role_for_new_users: string;
  created_at: string;
  updated_at: string;
};

/* SCIM tokens */
export type SCIMTokenRead = {
  id: string;
  name: string;
  created_at: string;
  expires_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
};
export type SCIMTokenCreateResponse = SCIMTokenRead & { token: string };
export type SCIMTokenCreate = { name: string; ttl_days?: number };

/* Magic-link */
export type MagicLinkPurpose = 'login' | 'password_reset' | 'email_verification';
export type MagicLinkRequest = {
  email: string;
  tenant_slug?: string | null;
  purpose?: MagicLinkPurpose;
};
export type MagicLinkConsumeResponse = {
  purpose: string;
  access_token?: string | null;
  refresh_token?: string | null;
  token_type: string;
  expires_in: number;
  reset_token?: string | null;
  email?: string | null;
};

export const ssoApi = {
  getConfig: () => api.get<SSOConfigOut>('/sso/config').then((r) => r.data),
  upsertConfig: (body: SSOConfigIn) =>
    api.post<SSOConfigOut>('/sso/config', body).then((r) => r.data),
  deleteConfig: () => api.delete('/sso/config').then(() => true),

  listScimTokens: () => api.get<SCIMTokenRead[]>('/sso/scim/tokens').then((r) => r.data),
  createScimToken: (body: SCIMTokenCreate) =>
    api.post<SCIMTokenCreateResponse>('/sso/scim/tokens', body).then((r) => r.data),
  revokeScimToken: (id: string) =>
    api.delete(`/sso/scim/tokens/${id}`).then(() => true),

  requestMagicLink: (body: MagicLinkRequest) =>
    api.post<{ ok: boolean }>('/auth/magic-link', body).then((r) => r.data),
  consumeMagicLink: (token: string) =>
    api
      .post<MagicLinkConsumeResponse>('/auth/magic-link/consume', { token })
      .then((r) => r.data),
};

/** Build the URL the browser should navigate to in order to start an SSO flow.
 *  The backend redirects from there to the IdP. */
export function oidcLoginUrl(tenantSlug: string, redirectAfter = '/'): string {
  const slug = encodeURIComponent(tenantSlug);
  const after = encodeURIComponent(redirectAfter);
  return `${API_BASE}/sso/oidc/login?tenant_slug=${slug}&redirect_after=${after}`;
}

export function samlLoginUrl(tenantSlug: string, redirectAfter = '/'): string {
  const slug = encodeURIComponent(tenantSlug);
  const after = encodeURIComponent(redirectAfter);
  return `${API_BASE}/sso/saml/login?tenant_slug=${slug}&redirect_after=${after}`;
}

export function samlMetadataUrl(tenantSlug: string): string {
  return `${API_BASE}/sso/saml/metadata?tenant_slug=${encodeURIComponent(tenantSlug)}`;
}

/** SCIM base URL — IdPs append /Users, /Groups etc. The actual SCIM protocol
 *  surface is mounted at the app root in main.py per RFC 7644 §3.1. */
export function scimBaseUrl(): string {
  // API_BASE is .../api/v1; strip that off to get the host root.
  const root = API_BASE.replace(/\/api\/v1\/?$/, '');
  return `${root}/scim/v2`;
}
