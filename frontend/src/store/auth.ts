import { create } from 'zustand';
import { api, tokenStore, type User, type UserRole } from '../lib/api';

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
  loading: boolean;
  initialized: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  loadMe: () => Promise<void>;
  refresh: () => Promise<void>;
  updateProfile: (patch: Partial<Pick<User, 'full_name' | 'department' | 'locale' | 'theme' | 'avatar_url'>>) => Promise<void>;
  uploadAvatar: (file: File) => Promise<void>;
  deleteAvatar: () => Promise<void>;
  changePassword: (current: string, next: string) => Promise<void>;
  logout: (callBackend?: boolean) => Promise<void>;
  hasRole: (...roles: UserRole[]) => boolean;
};

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  loading: true,
  initialized: false,
  async login(email, password) {
    const { data } = await api.post('/auth/login', { email, password });
    tokenStore.set(data.access_token, data.refresh_token);
    const me = await api.get<User>('/auth/me');
    set({ user: me.data, loading: false, initialized: true });
  },
  async register(payload) {
    await api.post('/auth/register', payload);
    await get().login(payload.email, payload.password);
  },
  async loadMe() {
    const token = tokenStore.getAccess();
    if (!token) {
      set({ user: null, loading: false, initialized: true });
      return;
    }
    try {
      const { data } = await api.get<User>('/auth/me');
      set({ user: data, loading: false, initialized: true });
    } catch {
      tokenStore.clear();
      set({ user: null, loading: false, initialized: true });
    }
  },
  async refresh() {
    const { data } = await api.get<User>('/auth/me');
    set({ user: data });
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
    const refresh = tokenStore.getRefresh();
    if (callBackend && tokenStore.getAccess()) {
      try {
        await api.post('/auth/logout', refresh ? { refresh_token: refresh } : {});
      } catch {
        /* ignore */
      }
    }
    tokenStore.clear();
    set({ user: null, loading: false, initialized: true });
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
