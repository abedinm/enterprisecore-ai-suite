import { api } from './api';

/* ---- Encryption / BYOK -------------------------------------------------- */

export type EncryptionKeyOut = {
  key_version: number;
  kms_provider: string;
  kms_key_ref: string | null;
  is_active: boolean;
  activated_at: string;
  rotated_at: string | null;
};

export type RotateOut = { job_id: string; new_key_version: number };

export type ByokIn = {
  kms_provider: 'server' | 'aws_kms' | 'gcp_kms' | 'azure_kv' | 'hcv_transit';
  kms_key_ref: string;
};

export const encryptionApi = {
  current: () => api.get<EncryptionKeyOut>('/encryption/key').then((r) => r.data),
  list: () => api.get<EncryptionKeyOut[]>('/encryption/keys').then((r) => r.data),
  rotate: () => api.post<RotateOut>('/encryption/rotate', {}).then((r) => r.data),
  byok: (body: ByokIn) => api.post<EncryptionKeyOut>('/encryption/byok', body).then((r) => r.data),
};

/* ---- Security policies (IP allowlist + audit streams) ------------------- */

export type SecurityPolicyOut = {
  ip_allowlist_cidrs: string[];
  ip_allowlist_enforced: boolean;
};

export type IpAllowlistIn = { cidrs: string[]; enforced: boolean };

export type AuditStreamType = 'webhook' | 'splunk_hec' | 'datadog_logs' | 'sumo_logic';

export type AuditStreamIn = {
  name: string;
  destination_type: AuditStreamType;
  url: string;
  credentials?: string | null;
  is_active?: boolean;
};

export type AuditStreamUpdate = Partial<AuditStreamIn>;

export type AuditStreamOut = {
  id: string;
  name: string;
  destination_type: string;
  url: string;
  is_active: boolean;
  last_success_at: string | null;
  last_error_at: string | null;
  last_error_message: string | null;
  consecutive_failures: number;
  created_at: string;
  updated_at: string;
};

export const securityPoliciesApi = {
  getPolicy: () => api.get<SecurityPolicyOut>('/security/policies').then((r) => r.data),
  updateIpAllowlist: (body: IpAllowlistIn) =>
    api.put<SecurityPolicyOut>('/security/policies/ip-allowlist', body).then((r) => r.data),
  listDestinations: () =>
    api.get<AuditStreamOut[]>('/security/audit-stream-destinations').then((r) => r.data),
  createDestination: (body: AuditStreamIn) =>
    api.post<AuditStreamOut>('/security/audit-stream-destinations', body).then((r) => r.data),
  updateDestination: (id: string, body: AuditStreamUpdate) =>
    api.patch<AuditStreamOut>(`/security/audit-stream-destinations/${id}`, body).then((r) => r.data),
  deleteDestination: (id: string) =>
    api.delete(`/security/audit-stream-destinations/${id}`).then(() => true),
  testDestination: (id: string) =>
    api
      .post<{ ok: boolean; error: string | null }>(`/security/audit-stream-destinations/${id}/test`)
      .then((r) => r.data),
};
