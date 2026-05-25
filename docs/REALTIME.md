# Realtime — WebSockets, SSE, Yjs

EnterpriseCore exposes three realtime transports. They live side-by-side
because each one is the right tool for a different audience.

| Transport     | Use it for                                                | Why                                          |
| ------------- | --------------------------------------------------------- | -------------------------------------------- |
| WebSocket     | Toasts, live conversation viewer, collaborative editing   | Full duplex, low latency                     |
| SSE           | Job-status updates                                        | Survives strict corporate proxies            |
| Yjs over WS   | Collaborative editing of Documents                        | CRDT — multiple writers without coordination |

## Endpoints

### WebSocket

- `ws://<host>/api/v1/ws/notifications` — per-user toast inbox and
  tenant-wide system events. Subscribes to ~17 event-bus types
  (`crm.deal.won`, `finance.invoice.paid`, `billing.payment.failed`,
  `ai.spend.threshold_crossed`, etc.) and forwards them as
  `{type: "notification", title, body, level, data}` frames.
- `ws://<host>/api/v1/ws/webchat/{bot_id}` — live conversation stream
  for a specific bot. The endpoint enforces ownership: only the bot's
  owner gets the socket open. Frames are `{type: "webchat.update", bot_id,
  conversation_id, ...}`.
- `ws://<host>/api/v1/ws/yjs/{document_id}` — CRDT relay for the
  Documents module. See "Yjs" below.

### SSE

- `GET /api/v1/sse/jobs` — `text/event-stream`. Receives every job
  lifecycle event (`jobs.queued`, `jobs.started`, `jobs.completed`,
  `jobs.failed`) for the authenticated user.

## Auth

WebSocket handshakes accept the access token from any of:

1. `?token=<jwt>` query string (default — what the frontend sends).
2. `Sec-WebSocket-Protocol: bearer.<jwt>` subprotocol header.
3. `__Host-access_token` / `access_token` cookie.

If no valid token is presented the server `accept()`s the connection
then closes with code **1008** (policy violation). The frontend client
treats 1008 as a hard failure and stops reconnecting until the user
re-authenticates.

SSE uses the standard HTTP bearer/cookie auth — same as every other API
endpoint.

## Tenant scoping

Every fan-out goes through `app.services.realtime.ConnectionManager`,
which indexes sockets under `(tenant_id, channel, user_id)`. An event
published by tenant A *cannot* reach a socket in tenant B's bucket —
the channel-lookup key includes the tenant id. Cross-tenant isolation
has a dedicated test in `tests/test_ws_notifications.py`.

## Heartbeat

Both directions send ping/pong frames every 30 seconds:

- Server sends `{"type": "ping", "ts": "..."}`. Client must reply
  `{"type": "pong"}`.
- Client also sends `{"type": "ping"}`. Server replies `{"type":
  "pong"}`.

A socket that hasn't received a pong in 60s is closed and replaced. The
frontend's `RealtimeClient` handles this transparently.

## Reconnect

Frontend `RealtimeClient` uses exponential backoff: **1s → 2s → 4s →
8s → 16s → 30s** (max). The header `RealtimeStatus` pill shows
`Live` / `Reconnecting` / `Offline`.

## Yjs collaborative editing

The `/ws/yjs/{document_id}` endpoint is a relay-plus-persistence layer.
Without `y-py` installed the server does NOT interpret the CRDT
protocol — it just:

1. Sends the persisted update log to a joining client so they can
   `Y.applyUpdate(updates)` to catch up.
2. Relays every subsequent binary frame to every other peer in the same
   room.
3. Appends the bytes to `yjs_documents.update_log` (debounced, every
   ~10s of dirty time).
4. On the last peer leaving the room, persists a final snapshot.

The Yjs Javascript library on the client handles all the merge logic,
state vectors, and awareness piggy-backing. When/if `y-py` is
installed, the server can graduate to a full CRDT-aware peer (compress
the update log into a state vector, garbage-collect tombstones).

### Schema

```
yjs_documents
    id              (ULID PK)
    tenant_id       (FK tenants, indexed)
    document_id     (FK in spirit — points at Documents-module row)
    document_kind   ("doc" | "wiki" | "marketing-post")
    state_vector    (binary — reserved for future y-py integration)
    update_log      (binary — concatenated CRDT updates)
    last_modified_by_id
    active_user_count
    created_at / updated_at
```

## Corporate proxy / firewall notes

Many corporate firewalls strip the `Upgrade: websocket` header, which
makes WebSocket connections never complete the handshake. Symptom: the
frontend `RealtimeStatus` pill stays on `Reconnecting` forever and the
network tab shows a 101 that never arrives.

Mitigation: the SSE endpoint at `/api/v1/sse/jobs` exists as a fallback
for **job status updates specifically** because that's the most common
"must work everywhere" requirement. Notifications and webchat live
streaming require WebSockets.

If you need notifications to work behind such a proxy: the existing
polling fallback (TanStack Query's `refetchInterval`) on the
Notifications page still works and stays accurate — just less
instant. We deliberately did NOT add an SSE notifications channel
because it would double our event-bus subscription surface for
marginal benefit on a population that's already shrinking.

## Frontend usage

```tsx
import { useWebSocket } from '../hooks/useWebSocket';

function MyComponent({ botId }: { botId: string }) {
  useWebSocket(`/ws/webchat/${botId}`, {
    enabled: Boolean(botId),
    onMessage(msg) {
      if (msg.type === 'webchat.update') {
        // ...
      }
    },
  });
}
```

For toasts there's nothing to wire by hand — `useRealtimeNotifications()`
is already mounted in `AppShell`.
