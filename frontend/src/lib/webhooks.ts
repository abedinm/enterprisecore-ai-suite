import { api } from './api';

export type EventTypeInfo = { type: string; module: string; description: string };

export type WebhookSubscriptionIn = {
  name: string;
  url: string;
  event_types?: string[];
  secret?: string | null;
  is_active?: boolean;
};

export type WebhookSubscriptionUpdate = {
  name?: string;
  url?: string;
  event_types?: string[];
  is_active?: boolean;
  rotate_secret?: boolean;
};

export type WebhookSubscriptionOut = {
  id: string;
  created_at: string;
  updated_at: string;
  name: string;
  url: string;
  event_types: string[];
  is_active: boolean;
  created_by_id: string | null;
  last_delivered_at: string | null;
  last_delivery_status: number | null;
  consecutive_failures: number;
  disabled_until: string | null;
};

export type WebhookSubscriptionCreated = WebhookSubscriptionOut & { secret: string };

export type WebhookDeliveryOut = {
  id: string;
  created_at: string;
  updated_at: string;
  subscription_id: string;
  event_id: string;
  event_type: string;
  payload_json: Record<string, unknown>;
  request_signature: string;
  delivered_at: string | null;
  response_status: number | null;
  response_body_excerpt: string | null;
  duration_ms: number | null;
  attempt_number: number;
  next_retry_at: string | null;
};

const PREFIX = '/webhooks';

export const webhooksApi = {
  eventTypes: () => api.get<EventTypeInfo[]>(`${PREFIX}/event-types`).then((r) => r.data),
  list: () => api.get<WebhookSubscriptionOut[]>(`${PREFIX}/subscriptions`).then((r) => r.data),
  get: (id: string) =>
    api.get<WebhookSubscriptionOut>(`${PREFIX}/subscriptions/${id}`).then((r) => r.data),
  create: (body: WebhookSubscriptionIn) =>
    api.post<WebhookSubscriptionCreated>(`${PREFIX}/subscriptions`, body).then((r) => r.data),
  update: (id: string, body: WebhookSubscriptionUpdate) =>
    api.patch<WebhookSubscriptionCreated>(`${PREFIX}/subscriptions/${id}`, body).then((r) => r.data),
  delete: (id: string) => api.delete(`${PREFIX}/subscriptions/${id}`).then(() => true),
  test: (id: string) =>
    api.post<{ event_id: string; status: string }>(`${PREFIX}/subscriptions/${id}/test`).then((r) => r.data),
  deliveries: (id: string, limit = 50) =>
    api
      .get<WebhookDeliveryOut[]>(`${PREFIX}/subscriptions/${id}/deliveries`, { params: { limit } })
      .then((r) => r.data),
  retry: (deliveryId: string) =>
    api.post<{ delivery_id: string; status: string }>(`${PREFIX}/deliveries/${deliveryId}/retry`).then((r) => r.data),
};
