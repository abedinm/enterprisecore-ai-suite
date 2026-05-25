// Generic WebSocket subscription hook — acquires/releases a shared
// connection for a given path and re-renders the host component when
// the connection status changes. The optional message handler is
// called for every inbound JSON frame (after server-side ping/pong
// has been stripped by the client wrapper).

import { useEffect, useRef, useState } from 'react';
import {
  acquireRealtime,
  releaseRealtime,
  type RealtimeMessage,
  type RealtimeStatus,
} from '../lib/realtime';

interface UseWebSocketOptions {
  // Set to false to skip opening the connection — useful for hooks
  // that only run for authenticated users; pass `enabled: !!user`.
  enabled?: boolean;
  // Called for every inbound message on the channel.
  onMessage?: (msg: RealtimeMessage) => void;
}

export function useWebSocket(path: string, opts: UseWebSocketOptions = {}) {
  const { enabled = true, onMessage } = opts;
  const [status, setStatus] = useState<RealtimeStatus>('disconnected');
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    if (!enabled || !path) {
      setStatus('disconnected');
      return;
    }
    const client = acquireRealtime(path);
    const offStatus = client.onStatus((s) => setStatus(s));
    const offMsg = client.subscribe((msg) => {
      onMessageRef.current?.(msg);
    });
    return () => {
      offStatus();
      offMsg();
      releaseRealtime(path);
    };
    // We deliberately omit `onMessage` from deps — it's captured in a
    // ref above so callers can pass inline arrow functions without
    // tearing down the subscription on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, enabled]);

  return { status };
}
