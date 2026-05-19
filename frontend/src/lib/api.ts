import axios, { AxiosError, type AxiosRequestConfig } from 'axios';

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8765/api/v1';

const ACCESS_KEY = 'ec_access_token';
const REFRESH_KEY = 'ec_refresh_token';

export const tokenStore = {
  getAccess: () => localStorage.getItem(ACCESS_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  set: (access: string, refresh: string) => {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear: () => {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 20000,
});

api.interceptors.request.use((config) => {
  const token = tokenStore.getAccess();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let refreshing: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refresh = tokenStore.getRefresh();
  if (!refresh) return null;
  try {
    const { data } = await axios.post(`${API_BASE}/auth/refresh`, { refresh_token: refresh });
    tokenStore.set(data.access_token, data.refresh_token);
    return data.access_token;
  } catch {
    tokenStore.clear();
    return null;
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as AxiosRequestConfig & { _retried?: boolean };
    if (!original || original._retried) throw error;
    const status = error.response?.status;
    const url = (original.url ?? '').toLowerCase();
    if (status === 401 && !url.includes('/auth/login') && !url.includes('/auth/refresh')) {
      original._retried = true;
      if (!refreshing) refreshing = refreshAccessToken();
      const access = await refreshing;
      refreshing = null;
      if (access) {
        original.headers = { ...(original.headers ?? {}), Authorization: `Bearer ${access}` };
        return api(original);
      }
      window.dispatchEvent(new CustomEvent('ec:auth:expired'));
    }
    throw error;
  },
);

export type UserRole = 'Admin' | 'Manager' | 'Employee' | 'Developer';

export type User = {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  department: string | null;
  avatar_url: string | null;
  theme: string;
  locale: string;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
};

export type ModuleGroup = {
  group: string;
  items: string[];
};

export type NotificationItem = {
  id: string;
  title: string;
  body: string;
  level: 'info' | 'success' | 'warning' | 'error' | string;
  link: string | null;
  is_read: boolean;
  created_at: string;
};

export type NotificationCounts = {
  total: number;
  unread: number;
};

export type SearchHit = {
  id: string;
  module: string;
  entity_type: string;
  entity_id: string;
  title: string;
  body: string;
  updated_at?: string | null;
};

export type SearchResponse = {
  items: SearchHit[];
  total: number;
  query: string;
};
