import { useState } from 'react';
import {
  BarChart3, Calendar, ClipboardList, Flag, Gauge, GanttChart, Kanban,
  LayoutPanelTop, Timer, Users2, Workflow,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { KanbanTab } from './KanbanTab';
import { GanttTab } from './GanttTab';
import { TimeTrackerTab } from './TimeTrackerTab';
import { SchedulerTab } from './SchedulerTab';
import { ResourcesTab } from './ResourcesTab';
import { MilestonesTab } from './MilestonesTab';
import { WorkloadTab } from './WorkloadTab';
import { SprintsTab } from './SprintsTab';
import { MeetingsTab } from './MeetingsTab';
import { ProjectsAnalyticsTab } from './ProjectsAnalyticsTab';

type TabKey =
  | 'analytics' | 'kanban' | 'gantt' | 'time' | 'scheduler'
  | 'resources' | 'milestones' | 'workload' | 'sprints' | 'meetings';

const tabs: { key: TabKey; label: string; icon: typeof Kanban }[] = [
  { key: 'analytics', label: 'Analytics', icon: Gauge },
  { key: 'kanban', label: 'Kanban', icon: Kanban },
  { key: 'gantt', label: 'Gantt', icon: GanttChart },
  { key: 'time', label: 'Time Tracker', icon: Timer },
  { key: 'scheduler', label: 'Scheduler', icon: Calendar },
  { key: 'resources', label: 'Resources', icon: Users2 },
  { key: 'milestones', label: 'Milestones', icon: Flag },
  { key: 'workload', label: 'Workload', icon: BarChart3 },
  { key: 'sprints', label: 'Sprints', icon: Workflow },
  { key: 'meetings', label: 'Meetings', icon: ClipboardList },
];

export function ProjectsPage() {
  const [active, setActive] = useState<TabKey>('analytics');
  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-brand-600">Module workspace</p>
        <h1 className="mt-1 flex items-center gap-2 text-3xl font-semibold">
          <LayoutPanelTop className="text-brand-600" size={26} />
          Project Management
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-muted">
          10 fully-offline planning tools — Kanban, Gantt, time tracking, scheduler, resource allocation,
          milestones, workload visualizer, sprint planner, meeting recorder, and project analytics.
        </p>
      </div>
      <div className="ec-card overflow-hidden">
        <div className="flex flex-wrap gap-1 border-b border-border bg-surface-muted px-2 py-2">
          {tabs.map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.key}
                onClick={() => setActive(t.key)}
                className={cn(
                  'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition',
                  active === t.key
                    ? 'bg-brand-600 text-white shadow-sm'
                    : 'text-ink-muted hover:bg-surface-elevated hover:text-ink',
                )}
              >
                <Icon size={15} /> {t.label}
              </button>
            );
          })}
        </div>
        <div className="p-5">
          {active === 'analytics' && <ProjectsAnalyticsTab />}
          {active === 'kanban' && <KanbanTab />}
          {active === 'gantt' && <GanttTab />}
          {active === 'time' && <TimeTrackerTab />}
          {active === 'scheduler' && <SchedulerTab />}
          {active === 'resources' && <ResourcesTab />}
          {active === 'milestones' && <MilestonesTab />}
          {active === 'workload' && <WorkloadTab />}
          {active === 'sprints' && <SprintsTab />}
          {active === 'meetings' && <MeetingsTab />}
        </div>
      </div>
    </div>
  );
}
