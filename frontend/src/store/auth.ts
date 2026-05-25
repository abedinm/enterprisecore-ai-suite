import { create } from 'zustand';
import { api, tokenStore, type User, type UserRole } from '../lib/api';
import type { TenantRead } from './../lib/tenant';

type RegisterPayload = {
  email: string;
  full_name: string;
  password: string;
  role?: UserRole;
  department?: string | null;
  locale?: string | null;
};

type AuthState = {
  user: User | null;
  tenant: TenantRead | null;
  loading: boolean;
  initialized: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  loadMe: () => Promise<void>;
  refresh: () => Promise<void>;
  setSession: (access: string, refresh: string, tenant?: TenantRead | null) => Promise<void>;
  setTenant: (tenant: TenantRead | null) => void;
  updateProfile: (patch: Partial<Pick<User, 'full_name' | 'department' | 'locale' | 'theme' | 'avatar_url'>>) => Promise<void>;
  uploadAvatar: (file: File) => Promise<void>;
  deleteAvatar: () => Promise<void>;
  changePassword: (current: string, next: string) => Promise<void>;
  logout: (callBackend?: boolean) => Promise<void>;
  hasRole: (...roles: UserRole[]) => boolean;
};

async function _loadTenantSilently(): Promise<TenantRead | null> {
  try {
    const r = await api.get<TenantRead>('/tenants/me');
    return r.data;
  } catch {
    return null;
  }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  tenant: null,
  loading: true,
  initialized: false,
  async login(email, password) {
    const { data } = await api.post('/auth/login', { email, password });
    tokenStore.set(data.access_token, data.refresh_token);
    const [me, tenant] = await Promise.all([
      api.get<User>('/auth/me'),
      _loadTenantSilently(),
    ]);
    set({ user: me.data, tenant, loading: false, initialized: true });
    // Fire the gamification refresh AFTER login resolves so any unlocked
    // achievements (welcome / first_login / streak) get their celebration.
    try {
      const { useGamification } = await import('./gamification');
      await useGamification.getState().refresh();
    } catch {
      /* gamification is optional — never break login */
    }
  },
  async register(payload) {
    await api.post('/auth/register', payload);
    await get().login(payload.email, payload.password);
  },
  async loadMe() {
    // Cookie mode (browser): we don't know if the cookie is present until we
    // ask the server. Electron mode: short-circuit on missing access token.
    if (!tokenStore.isCookieMode() && !tokenStore.getAccess()) {
      set({ user: null, tenant: null, loading: false, initialized: true });
      return;
    }
    try {
      const [me, tenant] = await Promise.all([
        api.get<User>('/auth/me'),
        _loadTenantSilently(),
      ]);
      set({ user: me.data, tenant, loading: false, initialized: true });
    } catch {
      tokenStore.clear();
      set({ user: null, tenant: null, loading: false, initialized: true });
    }
  },
  async refresh() {
    const { data } = await api.get<User>('/auth/me');
    set({ user: data });
  },
  async setSession(access, refresh, tenant) {
    tokenStore.set(access, refresh);
    const { data } = await api.get<User>('/auth/me');
    const finalTenant = tenant !== undefined ? tenant : await _loadTenantSilently();
    set({ user: data, tenant: finalTenant ?? null, loading: false, initialized: true });
  },
  setTenant(tenant) {
    set({ tenant });
  },
  async updateProfile(patch) {
    const { data } = await api.patch<User>('/auth/me', patch);
    set({ user: data });
  },
  async uploadAvatar(file) {
    const form = new FormData();
    form.append('file', file);
    const { data } = await api.post<User>('/auth/me/avatar', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    set({ user: data });
  },
  async deleteAvatar() {
    await api.delete('/auth/me/avatar');
    const user = get().user;
    if (user) set({ user: { ...user, avatar_url: null } });
  },
  async changePassword(current, next) {
    await api.post('/auth/me/password', { current_password: current, new_password: next });
    await get().logout(false);
  },
  async logout(callBackend = true) {
    if (callBackend) {
      // Cookie mode: server clears cookies; we don't need a body.
      // Electron mode: send the refresh token so it can be revoked.
      const refresh = tokenStore.getRefresh();
      try {
        await api.post('/auth/logout', refresh ? { refresh_token: refresh } : {});
      } catch {
        /* ignore */
      }
    }
    tokenStore.clear();
    set({ user: null, tenant: null, loading: false, initialized: true });
  },
  hasRole(...roles) {
    const user = get().user;
    return !!user && roles.includes(user.role);
  },
}));

if (typeof window !== 'undefined') {
  window.addEventListener('ec:auth:expired', () => {
    useAuthStore.getState().logout(false);
  });
}

/** Convenience hook — returns the tenant attached to the current session. */
export const useCurrentTenant = () => useAuthStore((s) => s.tenant);
