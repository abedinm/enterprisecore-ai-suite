import { useState } from 'react';
import {
  Users, Clock, CalendarOff, Star, Briefcase, ClipboardList,
  Network, FileBadge, GraduationCap, UserCircle2, AlertOctagon, BarChart3, UsersRound,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { EmployeesTab } from './EmployeesTab';
import { AttendanceTab } from './AttendanceTab';
import { LeaveTab } from './LeaveTab';
import { ReviewsTab } from './ReviewsTab';
import { RecruitmentTab } from './RecruitmentTab';
import { OnboardingTab } from './OnboardingTab';
import { OrgChartTab } from './OrgChartTab';
import { PayslipsTab } from './PayslipsTab';
import { TrainingTab } from './TrainingTab';
import { SelfServiceTab } from './SelfServiceTab';
import { DisciplineTab } from './DisciplineTab';
import { HRAnalyticsTab } from './HRAnalyticsTab';

type TabKey =
  | 'employees' | 'attendance' | 'leave' | 'reviews' | 'recruitment'
  | 'onboarding' | 'orgchart' | 'payslips' | 'training' | 'selfservice'
  | 'discipline' | 'analytics';

const tabs: { key: TabKey; label: string; icon: typeof Users }[] = [
  { key: 'employees', label: 'Employees', icon: Users },
  { key: 'attendance', label: 'Attendance', icon: Clock },
  { key: 'leave', label: 'Leave', icon: CalendarOff },
  { key: 'reviews', label: 'Reviews', icon: Star },
  { key: 'recruitment', label: 'Recruitment', icon: Briefcase },
  { key: 'onboarding', label: 'Onboarding', icon: ClipboardList },
  { key: 'orgchart', label: 'Org Chart', icon: Network },
  { key: 'payslips', label: 'Payslips', icon: FileBadge },
  { key: 'training', label: 'Training', icon: GraduationCap },
  { key: 'selfservice', label: 'Self Service', icon: UserCircle2 },
  { key: 'discipline', label: 'Discipline', icon: AlertOctagon },
  { key: 'analytics', label: 'Analytics', icon: BarChart3 },
];

export function HRPage() {
  const [active, setActive] = useState<TabKey>('employees');
  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-brand-600">Module workspace</p>
        <h1 className="mt-1 flex items-center gap-2 text-3xl font-semibold">
          <UsersRound className="text-brand-600" size={26} />
          Human Resources
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-muted">
          12 offline HR tools — employees, attendance, leave, reviews, recruitment, onboarding,
          org chart, payslips with PDF, training, self-service, discipline, and analytics.
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
          {active === 'employees' && <EmployeesTab />}
          {active === 'attendance' && <AttendanceTab />}
          {active === 'leave' && <LeaveTab />}
          {active === 'reviews' && <ReviewsTab />}
          {active === 'recruitment' && <RecruitmentTab />}
          {active === 'onboarding' && <OnboardingTab />}
          {active === 'orgchart' && <OrgChartTab />}
          {active === 'payslips' && <PayslipsTab />}
          {active === 'training' && <TrainingTab />}
          {active === 'selfservice' && <SelfServiceTab />}
          {active === 'discipline' && <DisciplineTab />}
          {active === 'analytics' && <HRAnalyticsTab />}
        </div>
      </div>
    </div>
  );
}
