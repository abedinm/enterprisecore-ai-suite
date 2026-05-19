export type Project = {
  id: string;
  name: string;
  description: string;
  status: string;
  start_date: string | null;
  end_date: string | null;
  budget: string;
  color: string;
  progress: number;
};

export type Task = {
  id: string;
  project_id: string | null;
  sprint_id: string | null;
  assignee_id: string | null;
  title: string;
  description: string;
  status: string;
  priority: string;
  due_date: string | null;
  start_date: string | null;
  estimated_hours: string;
  actual_hours: string;
  story_points: number;
  position: number;
  tags: string;
};

export type Sprint = {
  id: string;
  project_id: string;
  name: string;
  start_date: string;
  end_date: string;
  goal: string;
  status: string;
  capacity_points: number;
};

export type Milestone = {
  id: string;
  project_id: string;
  title: string;
  description: string;
  due_date: string | null;
  status: string;
  progress: number;
};

export type TimeEntry = {
  id: string;
  task_id: string | null;
  user_id: string | null;
  started_at: string;
  ended_at: string | null;
  minutes: number;
  notes: string;
  is_billable: boolean;
};

export type Meeting = {
  id: string;
  project_id: string | null;
  title: string;
  starts_at: string;
  ends_at: string | null;
  location: string | null;
  meeting_url: string | null;
  agenda: string;
  attendees: string;
  status: string;
};

export type MeetingMinute = {
  id: string;
  meeting_id: string;
  author_id: string | null;
  body: string;
  decisions: string;
  action_items: string;
};

export type Resource = {
  id: string;
  name: string;
  role: string;
  hourly_rate: string;
  capacity_hours_per_week: string;
  skills: string;
  is_active: boolean;
};

export type Allocation = {
  id: string;
  resource_id: string;
  project_id: string;
  start_date: string;
  end_date: string;
  allocation_pct: string;
  notes: string;
};

export const STATUS_COLUMNS = ['backlog', 'todo', 'in_progress', 'in_review', 'done'] as const;
export const PRIORITIES = ['low', 'medium', 'high', 'urgent'] as const;
export const PRIORITY_COLORS: Record<string, string> = {
  low: 'ec-badge-blue',
  medium: 'ec-badge',
  high: 'ec-badge-amber',
  urgent: 'ec-badge-rose',
};

export const PROJECT_STATUSES = ['active', 'on_hold', 'completed', 'archived'] as const;
