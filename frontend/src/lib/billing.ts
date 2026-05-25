import { api } from './api';

export type PlanCatalogItem = {
  plan: string;
  monthly_price_id: string;
  yearly_price_id: string;
  base_seats: number;
  monthly_usd: number;
  yearly_usd: number;
  formatted_monthly: string;
  formatted_yearly: string;
};

export type PlanCatalogResponse = {
  plans: PlanCatalogItem[];
  additional_seat_usd_monthly: number;
  ai_overage_usd_per_1k_tokens: number;
  self_managed: boolean;
};

export type TenantSubscriptionRead = {
  id: string;
  plan: string;
  status: string;
  seat_count: number;
  seat_quota: number;
  overage_seats: number;
  interval: string;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  canceled_at: string | null;
  trial_end: string | null;
  currency: string;
  amount_per_period: number | string;
  stripe_subscription_id: string | null;
  stripe_customer_id: string | null;
  created_at: string;
  updated_at: string;
};

export type UsageMeterRead = {
  meter_key: string;
  period_start: string;
  period_end: string;
  quantity: number | string;
  reported_to_stripe_at: string | null;
};

export type UsageResponse = {
  meters: UsageMeterRead[];
  ai_paid_usd_this_period: number;
  ai_monthly_cap_usd: number;
};

export type InvoiceRead = {
  id: string;
  number: string | null;
  status: string;
  amount_due_usd: number;
  amount_paid_usd: number;
  currency: string;
  created: number;
  period_start: number | null;
  period_end: number | null;
  hosted_invoice_url: string | null;
  invoice_pdf: string | null;
};

export type InvoiceListResponse = {
  invoices: InvoiceRead[];
  self_managed: boolean;
};

export type CheckoutIn = {
  plan: 'core' | 'edu' | 'verticals';
  interval?: 'month' | 'year';
  success_url?: string;
  cancel_url?: string;
};

export type CheckoutOut = { checkout_url: string; self_managed: boolean };
export type PortalOut = { portal_url: string; self_managed: boolean };

export type BillingActionResponse = {
  subscription: TenantSubscriptionRead | null;
  message: string;
};

const PREFIX = '/billing';

export const billingApi = {
  listPlans: () => api.get<PlanCatalogResponse>(`${PREFIX}/plans`).then((r) => r.data),
  getSubscription: () =>
    api.get<TenantSubscriptionRead | null>(`${PREFIX}/subscription`).then((r) => r.data),
  startCheckout: (body: CheckoutIn) =>
    api.post<CheckoutOut>(`${PREFIX}/checkout`, body).then((r) => r.data),
  openPortal: (returnUrl?: string) =>
    api.post<PortalOut>(`${PREFIX}/portal`, { return_url: returnUrl }).then((r) => r.data),
  cancel: () =>
    api.post<BillingActionResponse>(`${PREFIX}/cancel`, {}).then((r) => r.data),
  resume: () =>
    api.post<BillingActionResponse>(`${PREFIX}/resume`, {}).then((r) => r.data),
  usage: () => api.get<UsageResponse>(`${PREFIX}/usage`).then((r) => r.data),
  invoices: () => api.get<InvoiceListResponse>(`${PREFIX}/invoices`).then((r) => r.data),
};
