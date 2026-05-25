// Realtime client — thin wrapper around the native WebSocket API with
// exponential-backoff reconnect, heartbeat, and a subscribe/unsubscribe
// fan-out that lets multiple React hooks share one socket per channel.
//
// We deliberately keep this dependency-free (no socket.io, no rxjs). The
// surface is small enough that a vanilla EventTarget-style handler list
// is easier to reason about than another abstraction layer.

import { API_BASE, tokenStore } from './api';

export type RealtimeStatus = 'connecting' | 'connected' | 'disconnected';

export interface RealtimeMessage {
  type: string;
  [key: string]: unknown;
}

type Handler = (msg: RealtimeMessage) => void;

// Convert the HTTP base into a ws:// or wss:// origin. API_BASE looks
// like "http://127.0.0.1:8765/api/v1" — we keep the /api/v1 prefix so
// the resulting URL is "ws://127.0.0.1:8765/api/v1/ws/...".
function wsBaseFromHttp(httpBase: string): string {
  try {
    const u = new URL(httpBase, window.location.origin);
    const wsProto = u.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${wsProto}//${u.host}${u.pathname.replace(/\/$/, '')}`;
  } catch {
    // Best-effort fallback for unusual API_BASE values.
    return httpBase.replace(/^http/, 'ws');
  }
}

const WS_BASE = wsBaseFromHttp(API_BASE);

const BACKOFF_LADDER_MS = [1000, 2000, 4000, 8000, 16000, 30000] as const;
const HEARTBEAT_INTERVAL_MS = 30_000;
const HEARTBEAT_TIMEOUT_MS = 60_000;

export class RealtimeClient {
  readonly path: string;
  private ws: WebSocket | null = null;
  private status: RealtimeStatus = 'disconnected';
  private handlers = new Set<Handler>();
  private statusHandlers = new Set<(s: RealtimeStatus) => void>();
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private lastPongAt = 0;
  private stopped = false;

  // `path` is everything after the API base — e.g. "/ws/notifications"
  // or "/ws/webchat/<bot_id>".
  constructor(path: string) {
    this.path = path;
  }

  connect(): void {
    if (this.stopped) return;
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    this.setStatus('connecting');
    const token = tokenStore.getAccess();
    const url = `${WS_BASE}${this.path}${token ? `?token=${encodeURIComponent(token)}` : ''}`;
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch (err) {
      // Some browsers throw synchronously on bad URLs.
      this.scheduleReconnect();
      return;
    }
    this.ws = ws;

    ws.onopen = () => {
      this.reconnectAttempt = 0;
      this.lastPongAt = Date.now();
      this.setStatus('connected');
      this.startHeartbeat();
    };
    ws.onmessage = (ev) => {
      let parsed: RealtimeMessage;
      try {
        parsed = typeof ev.data === 'string' ? JSON.parse(ev.data) : { type: 'binary', data: ev.data };
      } catch {
        return;
      }
      if (parsed.type === 'ping') {
        // Server liveness probe — reply immediately.
        this.send({ type: 'pong' });
        this.lastPongAt = Date.now();
        return;
      }
      if (parsed.type === 'pong') {
        this.lastPongAt = Date.now();
        return;
      }
      this.fanOut(parsed);
    };
    ws.onclose = () => {
      this.stopHeartbeat();
      this.setStatus('disconnected');
      if (!this.stopped) this.scheduleReconnect();
    };
    ws.onerror = () => {
      // onclose follows; reconnect happens there.
    };
  }

  close(): void {
    this.stopped = true;
    this.stopHeartbeat();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      try {
        this.ws.close(1000, 'client-closing');
      } catch {
        /* noop */
      }
      this.ws = null;
    }
    this.setStatus('disconnected');
  }

  send(msg: Record<string, unknown>): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
    try {
      this.ws.send(JSON.stringify(msg));
      return true;
    } catch {
      return false;
    }
  }

  subscribe(handler: Handler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  onStatus(handler: (s: RealtimeStatus) => void): () => void {
    this.statusHandlers.add(handler);
    handler(this.status);
    return () => this.statusHandlers.delete(handler);
  }

  getStatus(): RealtimeStatus {
    return this.status;
  }

  // ----- internals --------------------------------------------------------
  private setStatus(s: RealtimeStatus): void {
    if (this.status === s) return;
    this.status = s;
    for (const h of this.statusHandlers) {
      try {
        h(s);
      } catch {
        /* noop */
      }
    }
  }

  private fanOut(msg: RealtimeMessage): void {
    for (const h of this.handlers) {
      try {
        h(msg);
      } catch {
        /* noop */
      }
    }
  }

  private scheduleReconnect(): void {
    if (this.stopped) return;
    if (this.reconnectTimer) return;
    const idx = Math.min(this.reconnectAttempt, BACKOFF_LADDER_MS.length - 1);
    const delay = BACKOFF_LADDER_MS[idx];
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      // If we haven't heard back from the server in too long, force a
      // reconnect — onclose handles the rebound.
      if (Date.now() - this.lastPongAt > HEARTBEAT_TIMEOUT_MS) {
        try {
          this.ws?.close(4000, 'heartbeat-timeout');
        } catch {
          /* noop */
        }
        return;
      }
      this.send({ type: 'ping' });
    }, HEARTBEAT_INTERVAL_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }
}

// ---------------------------------------------------------------------------
// Lightweight singleton registry — one socket per path. The first hook to
// ask for a path opens the connection; subsequent hooks share it. When the
// last hook unsubscribes we leave the socket open for a grace period so
// route transitions don't churn connections, then close it.
// ---------------------------------------------------------------------------
const CLIENT_CLOSE_GRACE_MS = 5000;
const clients = new Map<string, { client: RealtimeClient; refs: number; closeTimer: ReturnType<typeof setTimeout> | null }>();

export function acquireRealtime(path: string): RealtimeClient {
  let entry = clients.get(path);
  if (!entry) {
    entry = { client: new RealtimeClient(path), refs: 0, closeTimer: null };
    clients.set(path, entry);
    entry.client.connect();
  }
  if (entry.closeTimer) {
    clearTimeout(entry.closeTimer);
    entry.closeTimer = null;
  }
  entry.refs += 1;
  return entry.client;
}

export function releaseRealtime(path: string): void {
  const entry = clients.get(path);
  if (!entry) return;
  entry.refs = Math.max(0, entry.refs - 1);
  if (entry.refs === 0) {
    entry.closeTimer = setTimeout(() => {
      entry.client.close();
      clients.delete(path);
    }, CLIENT_CLOSE_GRACE_MS);
  }
}

export function getActiveConnectionCount(): number {
  let n = 0;
  for (const entry of clients.values()) {
    if (entry.client.getStatus() === 'connected') n += 1;
  }
  return n;
}
