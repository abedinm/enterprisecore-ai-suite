import { api } from './api';

export type DataCategory = {
  name: string;
  description: string;
  examples: string[];
  retention: string;
};

export type GdprExportJobOut = {
  id: string;
  user_id: string;
  status: string;
  download_url: string | null;
  expires_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  record_count: number;
  created_at: string;
};

export type GdprErasureReceiptOut = {
  id: string;
  created_at: string;
  updated_at: string;
  user_id: string;
  user_email_anonymized: string;
  requested_by_id: string | null;
  reason: string;
  fields_cleared: string[];
  records_anonymized: number;
  completed_at: string;
};

const PREFIX = '/gdpr';

export const gdprApi = {
  dataCategories: () => api.get<DataCategory[]>(`${PREFIX}/data-categories`).then((r) => r.data),
  requestExport: (userId?: string) =>
    api.post<GdprExportJobOut>(`${PREFIX}/export`, { user_id: userId }).then((r) => r.data),
  getExport: (jobId: string) =>
    api.get<GdprExportJobOut>(`${PREFIX}/export/${jobId}`).then((r) => r.data),
  erasureRequest: (userId: string, reason: string) =>
    api
      .post<GdprErasureReceiptOut>(`${PREFIX}/erasure-request`, { user_id: userId, reason })
      .then((r) => r.data),
  listReceipts: () =>
    api.get<GdprErasureReceiptOut[]>(`${PREFIX}/erasure-receipts`).then((r) => r.data),
};
