import { api } from './api';

/* -------------------------------------------------------------------------- */
/*  Types — mirror backend app/schemas/tenant.py                              */
/* -------------------------------------------------------------------------- */

export type TenantRead = {
  id: string;
  name: string;
  slug: string;
  plan: string;
  status: string;
  trial_ends_at: string | null;
  primary_contact_email: string;
  timezone: string;
  currency: string;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type TenantSignup = {
  name: string;
  slug: string;
  admin_email: string;
  admin_password: string;
  admin_full_name: string;
  primary_contact_email?: string | null;
  timezone?: string | null;
  currency?: string | null;
};

export type TenantUpdate = {
  name?: string;
  primary_contact_email?: string;
  timezone?: string;
  currency?: string;
  settings?: Record<string, unknown>;
};

export type TenantSignupResponse = {
  tenant: TenantRead;
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

export type TenantInviteIn = {
  email: string;
  role: string;
};

export type TenantInviteOut = {
  id: string;
  email: string;
  role: string;
  status: string;
  expires_at: string;
  token?: string | null;
};

export type TenantAcceptInvite = {
  token: string;
  password: string;
  full_name: string;
};

export type TenantUsage = {
  user_count: number;
  storage_mb: number;
  ai_spend_ytd_usd: number;
};

const PREFIX = '/tenants';

export const tenantApi = {
  signup: (body: TenantSignup) =>
    api.post<TenantSignupResponse>(`${PREFIX}/signup`, body).then((r) => r.data),
  me: () => api.get<TenantRead>(`${PREFIX}/me`).then((r) => r.data),
  updateMe: (body: TenantUpdate) =>
    api.patch<TenantRead>(`${PREFIX}/me`, body).then((r) => r.data),
  invite: (body: TenantInviteIn) =>
    api.post<TenantInviteOut>(`${PREFIX}/me/users/invite`, body).then((r) => r.data),
  acceptInvite: (body: TenantAcceptInvite) =>
    api.post<TenantSignupResponse>(`${PREFIX}/accept-invite`, body).then((r) => r.data),
  usage: () => api.get<TenantUsage>(`${PREFIX}/me/usage`).then((r) => r.data),
};

/** Slugify a tenant name into the canonical [a-z0-9-] form. */
export function tenantSlug(input: string): string {
  return input
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80);
}

/** Simple password-strength scoring used by the signup + accept-invite forms. */
export function passwordStrength(pw: string): { score: 0 | 1 | 2 | 3 | 4; label: string } {
  let score = 0;
  if (pw.length >= 10) score += 1;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score += 1;
  if (/\d/.test(pw)) score += 1;
  if (/[^a-zA-Z0-9]/.test(pw)) score += 1;
  const labels = ['Too short', 'Weak', 'Okay', 'Good', 'Strong'];
  return { score: score as 0 | 1 | 2 | 3 | 4, label: labels[score] };
}
