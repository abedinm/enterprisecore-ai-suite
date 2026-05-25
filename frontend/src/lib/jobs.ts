import { api } from './api';

export type JobOut = {
  id: string;
  created_at: string;
  updated_at: string;
  function_name: string;
  args_json: Record<string, unknown>;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  queue_name: string;
  attempts: number;
  last_error: string | null;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  result_excerpt: string | null;
  rq_job_id: string | null;
  created_by_id: string | null;
};

export type JobAttemptOut = {
  id: string;
  created_at: string;
  updated_at: string;
  job_id: string;
  attempt_number: number;
  status: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  error_message: string | null;
};

export type JobDetailOut = JobOut & { attempts_history: JobAttemptOut[] };

export type JobStatsOut = {
  queued: number;
  running: number;
  completed_today: number;
  failed_today: number;
  cancelled_today: number;
  total: number;
};

export const jobsApi = {
  list: (params?: { status?: string; function_name?: string; limit?: number; offset?: number }) =>
    api.get<JobOut[]>('/jobs', { params }).then((r) => r.data),
  get: (id: string) => api.get<JobDetailOut>(`/jobs/${id}`).then((r) => r.data),
  stats: () => api.get<JobStatsOut>('/jobs/stats').then((r) => r.data),
  cancel: (id: string) => api.post(`/jobs/${id}/cancel`).then((r) => r.data),
  retry: (id: string) => api.post(`/jobs/${id}/retry`).then((r) => r.data),
};
