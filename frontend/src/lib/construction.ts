import { api } from './api';
import { formatDate, formatNumber } from './format';

/* -------------------------------------------------------------------------- */
/*  Shared types                                                              */
/* -------------------------------------------------------------------------- */

export type ProjectType = 'residential' | 'commercial' | 'industrial' | 'infrastructure';
export type RiskCategory = 'safety' | 'financial' | 'schedule' | 'quality' | 'regulatory' | 'environmental';
export type ContractType = 'FIDIC' | 'NEC' | 'JCT' | 'AIA' | 'custom';
export type InsuranceType = 'CAR' | 'PI' | 'PL' | 'EL' | 'marine' | 'other';

/* -------------------------------------------------------------------------- */
/*  Project                                                                   */
/* -------------------------------------------------------------------------- */

export type ConstructionProject = {
  id: string;
  name: string;
  client_name: string;
  location: string;
  project_type: ProjectType;
  contract_value: string;
  currency: string;
  start_date: string;
  expected_end_date: string;
  actual_end_date: string | null;
  status: string;
  description?: string | null;
};
export type ConstructionProjectInput = Omit<ConstructionProject, 'id'>;

/* -------------------------------------------------------------------------- */
/*  Risks                                                                     */
/* -------------------------------------------------------------------------- */

export type Risk = {
  id: string;
  title: string;
  description?: string | null;
  category: RiskCategory;
  probability: number;        // 1-5
  impact: number;             // 1-5
  score: number;              // computed
  mitigation_plan?: string | null;
  owner_id?: string | null;
  owner_name?: string | null;
  status: string;
  identified_at: string;
  due_date?: string | null;
};
export type RiskInput = Omit<Risk, 'id' | 'score' | 'owner_name'>;

/* -------------------------------------------------------------------------- */
/*  Schedule                                                                  */
/* -------------------------------------------------------------------------- */

export type ScheduleTask = {
  id: string;
  name: string;
  description?: string | null;
  parent_task_id: string | null;
  start_date: string;
  end_date: string;
  duration_days: number;
  assigned_to_id?: string | null;
  progress_percent: number;
  status: string;
};
export type ScheduleTaskInput = Omit<ScheduleTask, 'id'>;

export type ScheduleDependency = {
  id: string;
  predecessor_id: string;
  successor_id: string;
  type?: string;       // FS / SS / FF / SF
  lag_days?: number;
};
export type ScheduleDependencyInput = Omit<ScheduleDependency, 'id'>;

/* -------------------------------------------------------------------------- */
/*  Milestones                                                                */
/* -------------------------------------------------------------------------- */

export type Milestone = {
  id: string;
  name: string;
  planned_date: string;
  actual_date: string | null;
  status: string;
  payment_trigger: boolean;
  payment_amount: string | null;
  notes?: string | null;
};
export type MilestoneInput = Omit<Milestone, 'id'>;

/* -------------------------------------------------------------------------- */
/*  Progress reports                                                          */
/* -------------------------------------------------------------------------- */

export type ProgressReport = {
  id: string;
  report_date: string;
  overall_progress_percent: number;
  narrative: string;
  reported_by_id?: string | null;
  photos: string[];
  weather_conditions?: string | null;
  workforce_count?: number | null;
};
export type ProgressReportInput = Omit<ProgressReport, 'id'>;

/* -------------------------------------------------------------------------- */
/*  Permits                                                                   */
/* -------------------------------------------------------------------------- */

export type Permit = {
  id: string;
  permit_type: string;
  issuing_authority: string;
  application_date: string;
  approval_date: string | null;
  expiry_date: string | null;
  status: string;
  reference_number?: string | null;
  conditions?: string | null;
};
export type PermitInput = Omit<Permit, 'id'>;

/* -------------------------------------------------------------------------- */
/*  Site instructions                                                         */
/* -------------------------------------------------------------------------- */

export type SiteInstruction = {
  id: string;
  number: string;
  title: string;
  description: string;
  issued_by_id?: string | null;
  issued_to: string;
  issued_at: string;
  response_required_by?: string | null;
  status: string;
  response: string | null;
  responded_at: string | null;
};
export type SiteInstructionInput = Omit<SiteInstruction, 'id' | 'number'>;

/* -------------------------------------------------------------------------- */
/*  Variations                                                                */
/* -------------------------------------------------------------------------- */

export type Variation = {
  id: string;
  number: string;
  title: string;
  description: string;
  requested_by: string;
  cost_impact: string;       // signed Decimal string
  time_impact_days: number;
  status: string;
  justification?: string | null;
  submitted_at: string;
  decided_at: string | null;
};
export type VariationInput = Omit<Variation, 'id' | 'number'>;

/* -------------------------------------------------------------------------- */
/*  EOT (Extension of Time) requests                                          */
/* -------------------------------------------------------------------------- */

export type EOTRequest = {
  id: string;
  requested_days: number;
  reason: string;
  supporting_evidence?: string | null;
  claim_date: string;
  status: string;
  granted_days: number | null;
  decided_at: string | null;
  decision_notes?: string | null;
};
export type EOTRequestInput = Omit<EOTRequest, 'id'>;

/* -------------------------------------------------------------------------- */
/*  Contracts                                                                 */
/* -------------------------------------------------------------------------- */

export type Contract = {
  id: string;
  contract_number: string;
  contract_type: ContractType;
  counterparty: string;
  value: string;
  currency: string;
  signed_date: string;
  start_date: string;
  end_date: string;
  retention_percent: number;
  defects_liability_period_days: number;
  payment_terms?: string | null;
};
export type ContractInput = Omit<Contract, 'id'>;

/* -------------------------------------------------------------------------- */
/*  RACI                                                                      */
/* -------------------------------------------------------------------------- */

export type RaciEntry = {
  id: string;
  activity: string;
  responsible_user_id?: string | null;
  accountable_user_id?: string | null;
  consulted: string[];
  informed: string[];
  notes?: string | null;
};
export type RaciEntryInput = Omit<RaciEntry, 'id'>;

/* -------------------------------------------------------------------------- */
/*  Insurance                                                                 */
/* -------------------------------------------------------------------------- */

export type Insurance = {
  id: string;
  insurance_type: InsuranceType;
  provider: string;
  policy_number: string;
  sum_insured: string;
  currency: string;
  start_date: string;
  expiry_date: string;
  premium_amount?: string | null;
  renewal_reminder_days: number;
};
export type InsuranceInput = Omit<Insurance, 'id'>;

/* -------------------------------------------------------------------------- */
/*  Toolbox talks                                                             */
/* -------------------------------------------------------------------------- */

export type ToolboxTalk = {
  id: string;
  topic: string;
  conducted_by_id?: string | null;
  conducted_at: string;
  attendees_count: number;
  key_points: string;
  attachments: string[];
  notes?: string | null;
};
export type ToolboxTalkInput = Omit<ToolboxTalk, 'id'>;

/* -------------------------------------------------------------------------- */
/*  Dashboard rollup                                                          */
/* -------------------------------------------------------------------------- */

export type RiskCounts = {
  low: number;
  medium: number;
  high: number;
  critical: number;
};

export type DashboardRollup = {
  project: ConstructionProject;
  /** Risks bucketed by computed severity (low/medium/high/critical). */
  risks_by_severity: RiskCounts;
  schedule_progress_percent: number;
  upcoming_milestones: Milestone[];
  /** Count of open variations. */
  open_variations_count: number;
  /** Sum of cost_impact across all open variations, formatted as Decimal string. */
  open_variations_cost_impact: string;
  pending_eot_days: number;
  expiring_insurances: Insurance[];
  recent_site_instructions: SiteInstruction[];
  latest_progress_report: ProgressReport | null;
};

/** Raw backend shape — the API uses slightly different field names than the
 * frontend type above. ``getDashboard`` normalises these into ``DashboardRollup``
 * so individual pages don't have to know about the wire format. */
type DashboardRollupRaw = {
  project: ConstructionProject;
  risk_buckets: RiskCounts & { total: number };
  schedule_progress_percent: number;
  upcoming_milestones: Milestone[];
  open_variations: Variation[];
  open_variations_cost_impact_total: string;
  pending_eot_days: number;
  expiring_insurances: Insurance[];
  recent_site_instructions: SiteInstruction[];
  latest_progress_report: ProgressReport | null;
};

/* -------------------------------------------------------------------------- */
/*  API surface                                                               */
/* -------------------------------------------------------------------------- */

const PREFIX = '/construction';
const project = (id: string) => `${PREFIX}/projects/${id}`;

export const constructionApi = {
  /* ---------- Projects ---------- */
  listProjects: () =>
    api.get<ConstructionProject[]>(`${PREFIX}/projects`).then((r) => r.data),
  getProject: (id: string) =>
    api.get<ConstructionProject>(project(id)).then((r) => r.data),
  createProject: (body: ConstructionProjectInput) =>
    api.post<ConstructionProject>(`${PREFIX}/projects`, body).then((r) => r.data),
  updateProject: (id: string, body: Partial<ConstructionProjectInput>) =>
    api.patch<ConstructionProject>(project(id), body).then((r) => r.data),
  deleteProject: (id: string) =>
    api.delete(project(id)).then(() => true),

  /* ---------- Dashboard rollup ---------- */
  getDashboard: (id: string): Promise<DashboardRollup> =>
    api.get<DashboardRollupRaw>(`${project(id)}/dashboard`).then((r) => {
      const raw = r.data;
      // Normalise wire-format → frontend shape. Backend uses snake_case names
      // that differ slightly from the frontend's; we paper over that here so
      // page components don't have to know about the wire format.
      return {
        project: raw.project,
        risks_by_severity: {
          low: raw.risk_buckets?.low ?? 0,
          medium: raw.risk_buckets?.medium ?? 0,
          high: raw.risk_buckets?.high ?? 0,
          critical: raw.risk_buckets?.critical ?? 0,
        },
        schedule_progress_percent: raw.schedule_progress_percent ?? 0,
        upcoming_milestones: raw.upcoming_milestones ?? [],
        open_variations_count: (raw.open_variations ?? []).length,
        open_variations_cost_impact: raw.open_variations_cost_impact_total ?? '0',
        pending_eot_days: raw.pending_eot_days ?? 0,
        expiring_insurances: raw.expiring_insurances ?? [],
        recent_site_instructions: raw.recent_site_instructions ?? [],
        latest_progress_report: raw.latest_progress_report ?? null,
      };
    }),

  /* ---------- Risks ---------- */
  listRisks: (id: string) =>
    api.get<Risk[]>(`${project(id)}/risks`).then((r) => r.data),
  createRisk: (id: string, body: RiskInput) =>
    api.post<Risk>(`${project(id)}/risks`, body).then((r) => r.data),
  updateRisk: (id: string, riskId: string, body: Partial<RiskInput>) =>
    api.patch<Risk>(`${project(id)}/risks/${riskId}`, body).then((r) => r.data),
  deleteRisk: (id: string, riskId: string) =>
    api.delete(`${project(id)}/risks/${riskId}`).then(() => true),

  /* ---------- Schedule ---------- */
  listScheduleTasks: (id: string) =>
    api.get<ScheduleTask[]>(`${project(id)}/schedule/tasks`).then((r) => r.data),
  createScheduleTask: (id: string, body: ScheduleTaskInput) =>
    api.post<ScheduleTask>(`${project(id)}/schedule/tasks`, body).then((r) => r.data),
  updateScheduleTask: (id: string, taskId: string, body: Partial<ScheduleTaskInput>) =>
    api.patch<ScheduleTask>(`${project(id)}/schedule/tasks/${taskId}`, body).then((r) => r.data),
  deleteScheduleTask: (id: string, taskId: string) =>
    api.delete(`${project(id)}/schedule/tasks/${taskId}`).then(() => true),

  listScheduleDependencies: (id: string) =>
    api.get<ScheduleDependency[]>(`${project(id)}/schedule/dependencies`).then((r) => r.data),
  createScheduleDependency: (id: string, body: ScheduleDependencyInput) =>
    api.post<ScheduleDependency>(`${project(id)}/schedule/dependencies`, body).then((r) => r.data),
  deleteScheduleDependency: (id: string, depId: string) =>
    api.delete(`${project(id)}/schedule/dependencies/${depId}`).then(() => true),

  /* ---------- Milestones ---------- */
  listMilestones: (id: string) =>
    api.get<Milestone[]>(`${project(id)}/milestones`).then((r) => r.data),
  createMilestone: (id: string, body: MilestoneInput) =>
    api.post<Milestone>(`${project(id)}/milestones`, body).then((r) => r.data),
  updateMilestone: (id: string, msId: string, body: Partial<MilestoneInput>) =>
    api.patch<Milestone>(`${project(id)}/milestones/${msId}`, body).then((r) => r.data),
  deleteMilestone: (id: string, msId: string) =>
    api.delete(`${project(id)}/milestones/${msId}`).then(() => true),

  /* ---------- Progress reports ---------- */
  listProgressReports: (id: string) =>
    api.get<ProgressReport[]>(`${project(id)}/progress-reports`).then((r) => r.data),
  createProgressReport: (id: string, body: ProgressReportInput) =>
    api.post<ProgressReport>(`${project(id)}/progress-reports`, body).then((r) => r.data),
  deleteProgressReport: (id: string, reportId: string) =>
    api.delete(`${project(id)}/progress-reports/${reportId}`).then(() => true),

  /* ---------- Permits ---------- */
  listPermits: (id: string) =>
    api.get<Permit[]>(`${project(id)}/permits`).then((r) => r.data),
  createPermit: (id: string, body: PermitInput) =>
    api.post<Permit>(`${project(id)}/permits`, body).then((r) => r.data),
  updatePermit: (id: string, permitId: string, body: Partial<PermitInput>) =>
    api.patch<Permit>(`${project(id)}/permits/${permitId}`, body).then((r) => r.data),
  deletePermit: (id: string, permitId: string) =>
    api.delete(`${project(id)}/permits/${permitId}`).then(() => true),

  /* ---------- Site instructions ---------- */
  listSiteInstructions: (id: string) =>
    api.get<SiteInstruction[]>(`${project(id)}/site-instructions`).then((r) => r.data),
  createSiteInstruction: (id: string, body: SiteInstructionInput) =>
    api.post<SiteInstruction>(`${project(id)}/site-instructions`, body).then((r) => r.data),
  updateSiteInstruction: (id: string, siId: string, body: Partial<SiteInstructionInput>) =>
    api.patch<SiteInstruction>(`${project(id)}/site-instructions/${siId}`, body).then((r) => r.data),
  deleteSiteInstruction: (id: string, siId: string) =>
    api.delete(`${project(id)}/site-instructions/${siId}`).then(() => true),

  /* ---------- Variations ---------- */
  listVariations: (id: string) =>
    api.get<Variation[]>(`${project(id)}/variations`).then((r) => r.data),
  createVariation: (id: string, body: VariationInput) =>
    api.post<Variation>(`${project(id)}/variations`, body).then((r) => r.data),
  updateVariation: (id: string, varId: string, body: Partial<VariationInput>) =>
    api.patch<Variation>(`${project(id)}/variations/${varId}`, body).then((r) => r.data),
  deleteVariation: (id: string, varId: string) =>
    api.delete(`${project(id)}/variations/${varId}`).then(() => true),

  /* ---------- EOT requests ---------- */
  listEotRequests: (id: string) =>
    api.get<EOTRequest[]>(`${project(id)}/eot-requests`).then((r) => r.data),
  createEotRequest: (id: string, body: EOTRequestInput) =>
    api.post<EOTRequest>(`${project(id)}/eot-requests`, body).then((r) => r.data),
  updateEotRequest: (id: string, eotId: string, body: Partial<EOTRequestInput>) =>
    api.patch<EOTRequest>(`${project(id)}/eot-requests/${eotId}`, body).then((r) => r.data),
  deleteEotRequest: (id: string, eotId: string) =>
    api.delete(`${project(id)}/eot-requests/${eotId}`).then(() => true),

  /* ---------- Contracts ---------- */
  listContracts: (id: string) =>
    api.get<Contract[]>(`${project(id)}/contracts`).then((r) => r.data),
  createContract: (id: string, body: ContractInput) =>
    api.post<Contract>(`${project(id)}/contracts`, body).then((r) => r.data),
  updateContract: (id: string, contractId: string, body: Partial<ContractInput>) =>
    api.patch<Contract>(`${project(id)}/contracts/${contractId}`, body).then((r) => r.data),
  deleteContract: (id: string, contractId: string) =>
    api.delete(`${project(id)}/contracts/${contractId}`).then(() => true),

  /* ---------- RACI ---------- */
  listRaci: (id: string) =>
    api.get<RaciEntry[]>(`${project(id)}/raci`).then((r) => r.data),
  createRaciEntry: (id: string, body: RaciEntryInput) =>
    api.post<RaciEntry>(`${project(id)}/raci`, body).then((r) => r.data),
  updateRaciEntry: (id: string, raciId: string, body: Partial<RaciEntryInput>) =>
    api.patch<RaciEntry>(`${project(id)}/raci/${raciId}`, body).then((r) => r.data),
  deleteRaciEntry: (id: string, raciId: string) =>
    api.delete(`${project(id)}/raci/${raciId}`).then(() => true),

  /* ---------- Insurance ---------- */
  listInsurances: (id: string) =>
    api.get<Insurance[]>(`${project(id)}/insurances`).then((r) => r.data),
  createInsurance: (id: string, body: InsuranceInput) =>
    api.post<Insurance>(`${project(id)}/insurances`, body).then((r) => r.data),
  updateInsurance: (id: string, insId: string, body: Partial<InsuranceInput>) =>
    api.patch<Insurance>(`${project(id)}/insurances/${insId}`, body).then((r) => r.data),
  deleteInsurance: (id: string, insId: string) =>
    api.delete(`${project(id)}/insurances/${insId}`).then(() => true),

  /* ---------- Toolbox talks ---------- */
  listToolboxTalks: (id: string) =>
    api.get<ToolboxTalk[]>(`${project(id)}/toolbox-talks`).then((r) => r.data),
  createToolboxTalk: (id: string, body: ToolboxTalkInput) =>
    api.post<ToolboxTalk>(`${project(id)}/toolbox-talks`, body).then((r) => r.data),
  deleteToolboxTalk: (id: string, talkId: string) =>
    api.delete(`${project(id)}/toolbox-talks/${talkId}`).then(() => true),
};

/* -------------------------------------------------------------------------- */
/*  Static option lists & helpers                                             */
/* -------------------------------------------------------------------------- */

export const PROJECT_TYPE_OPTIONS: { value: ProjectType; label: string }[] = [
  { value: 'residential', label: 'Residential' },
  { value: 'commercial', label: 'Commercial' },
  { value: 'industrial', label: 'Industrial' },
  { value: 'infrastructure', label: 'Infrastructure' },
];

export const RISK_CATEGORY_OPTIONS: { value: RiskCategory; label: string }[] = [
  { value: 'safety', label: 'Safety' },
  { value: 'financial', label: 'Financial' },
  { value: 'schedule', label: 'Schedule' },
  { value: 'quality', label: 'Quality' },
  { value: 'regulatory', label: 'Regulatory' },
  { value: 'environmental', label: 'Environmental' },
];

export const CONTRACT_TYPE_OPTIONS: { value: ContractType; label: string }[] = [
  { value: 'FIDIC', label: 'FIDIC' },
  { value: 'NEC', label: 'NEC' },
  { value: 'JCT', label: 'JCT' },
  { value: 'AIA', label: 'AIA' },
  { value: 'custom', label: 'Custom' },
];

export const INSURANCE_TYPE_OPTIONS: { value: InsuranceType; label: string }[] = [
  { value: 'CAR', label: 'Contractors All Risks (CAR)' },
  { value: 'PI', label: 'Professional Indemnity (PI)' },
  { value: 'PL', label: 'Public Liability (PL)' },
  { value: 'EL', label: 'Employers Liability (EL)' },
  { value: 'marine', label: 'Marine Cargo' },
  { value: 'other', label: 'Other' },
];

/** Severity bucket from risk score (probability * impact, 1-25). */
export type RiskSeverity = 'low' | 'medium' | 'high' | 'critical';

export function riskSeverity(score: number): RiskSeverity {
  if (score >= 17) return 'critical';
  if (score >= 11) return 'high';
  if (score >= 6) return 'medium';
  return 'low';
}

export function riskSeverityBadge(severity: RiskSeverity): string {
  switch (severity) {
    case 'critical': return 'ec-badge-rose';
    case 'high': return 'ec-badge-amber';
    case 'medium': return 'ec-badge-blue';
    case 'low':
    default: return 'ec-badge-green';
  }
}

/** Cell color for the 5x5 risk heatmap (probability × impact). */
export function heatmapCellClass(probability: number, impact: number): string {
  const score = probability * impact;
  const sev = riskSeverity(score);
  switch (sev) {
    case 'critical': return 'bg-rose-500/80 text-white';
    case 'high': return 'bg-amber-500/70 text-white';
    case 'medium': return 'bg-blue-500/60 text-white';
    case 'low':
    default: return 'bg-emerald-500/50 text-white';
  }
}

/** Format an ISO date as a locale-friendly short date. */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  return formatDate(iso);
}

/** Days remaining until an ISO date (positive = future, negative = past). */
export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const target = new Date(iso).getTime();
  if (Number.isNaN(target)) return null;
  const now = Date.now();
  return Math.floor((target - now) / 86_400_000);
}

/** Pretty money: "1,234,567 USD" — non-locale-aware on purpose so values match the backend. */
export function formatMoney(value: string | null | undefined, currency = ''): string {
  if (value === null || value === undefined || value === '') return '—';
  const num = Number(value);
  if (Number.isNaN(num)) return value;
  const fixed = formatNumber(num, undefined, { maximumFractionDigits: 2 });
  return currency ? `${fixed} ${currency}` : fixed;
}
