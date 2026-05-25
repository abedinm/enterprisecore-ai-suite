import axios, { AxiosError, type AxiosRequestConfig } from 'axios';

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8765/api/v1';

// ---------------------------------------------------------------------------
// Auth-token storage
//
// Browser builds use httpOnly SameSite=Lax cookies set by the backend — tokens
// are never accessible to JavaScript (no XSS exfiltration). The cookie is
// transmitted automatically via `withCredentials: true`.
//
// The packaged Electron build runs from a `file://` origin which can't carry
// cookies cross-origin to a local FastAPI on 127.0.0.1. For that case ONLY we
// fall back to in-memory storage (never localStorage — XSS-safe) and send a
// Bearer header. Detected via `window.electron` (set by Electron preload) or
// the `file:` protocol.
//
// Anti-CSRF: the backend mirrors a non-httpOnly `csrf_token` cookie. We read
// it in the request interceptor and echo it as `X-CSRF-Token` for every
// mutating request — double-submit pattern.
// ---------------------------------------------------------------------------

declare global {
  interface Window {
    electron?: { isElectron: true };
  }
}

const IS_ELECTRON =
  typeof window !== 'undefined' &&
  (Boolean(window.electron?.isElectron) || window.location.protocol === 'file:');

// Electron-only in-memory token cache (kills XSS exfil; lost on app close — by design).
let electronAccess: string | null = null;
let electronRefresh: string | null = null;

export const tokenStore = {
  getAccess: () => (IS_ELECTRON ? electronAccess : null),
  getRefresh: () => (IS_ELECTRON ? electronRefresh : null),
  set: (access: string, refresh: string) => {
    if (IS_ELECTRON) {
      electronAccess = access;
      electronRefresh = refresh;
    }
    // In browser mode the backend has already set httpOnly cookies on the
    // response — there's nothing to store client-side.
  },
  clear: () => {
    electronAccess = null;
    electronRefresh = null;
  },
  isCookieMode: () => !IS_ELECTRON,
};

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const target = name + '=';
  for (const c of document.cookie.split(';')) {
    const t = c.trim();
    if (t.startsWith(target)) return decodeURIComponent(t.slice(target.length));
  }
  return null;
}

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 20000,
  withCredentials: true, // send/receive httpOnly cookies
});

const MUTATING_METHODS = new Set(['post', 'put', 'patch', 'delete']);

api.interceptors.request.use((config) => {
  // Electron Bearer fallback
  if (IS_ELECTRON) {
    const token = electronAccess;
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  // Browser CSRF double-submit
  const method = (config.method ?? 'get').toLowerCase();
  if (MUTATING_METHODS.has(method)) {
    const csrf = readCookie('csrf_token');
    if (csrf) config.headers['X-CSRF-Token'] = csrf;
  }
  return config;
});

let refreshing: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  try {
    // Cookie mode: body is empty, refresh cookie carries the token.
    // Electron mode: body carries the token.
    const body = IS_ELECTRON && electronRefresh ? { refresh_token: electronRefresh } : {};
    const { data } = await axios.post(`${API_BASE}/auth/refresh`, body, {
      withCredentials: true,
    });
    if (IS_ELECTRON) {
      electronAccess = data.access_token;
      electronRefresh = data.refresh_token;
      return data.access_token;
    }
    // Browser: the new cookies are now set; any sentinel non-empty string
    // tells the retry path "you may proceed".
    return data.access_token ?? 'cookie';
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
        if (IS_ELECTRON) {
          original.headers = { ...(original.headers ?? {}), Authorization: `Bearer ${access}` };
        }
        return api(original);
      }
      window.dispatchEvent(new CustomEvent('ec:auth:expired'));
    }
    throw error;
  },
);

export type UserRole =
  | 'Admin'
  | 'Manager'
  | 'Employee'
  | 'Developer'
  // Academic SKU (+EDU) roles. Mirror of backend app/models/user.py UserRole.
  | 'Student'
  | 'Teacher'
  | 'Registrar'
  | 'Dean';

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

// New FTS5-backed GET /search response shape.
export type FtsSearchResult = {
  entity_type: string;
  entity_id: string;
  title: string;
  subtitle: string;
  body_excerpt: string;
  rank: number;
  full?: Record<string, unknown>;
};

export type FtsSearchResponse = {
  results: FtsSearchResult[];
  total: number;
  query: string;
};
