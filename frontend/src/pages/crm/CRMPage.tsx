import { useState } from 'react';
import {
  Building2, Users, Target, Workflow, Phone, MessageSquare, FileSignature, FileText,
  Receipt, Layers, Send, BarChart3,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { LeadsTab } from './LeadsTab';
import { PipelineTab } from './PipelineTab';
import { CustomersTab } from './CustomersTab';
import { FollowUpsTab } from './FollowUpsTab';
import { ForecastTab } from './ForecastTab';
import { CommLogTab } from './CommLogTab';
import { ContractsTab } from './ContractsTab';
import { ProposalsTab } from './ProposalsTab';
import { QuotesTab } from './QuotesTab';
import { SegmentsTab } from './SegmentsTab';
import { CampaignsTab } from './CampaignsTab';
import { CRMAnalyticsTab } from './CRMAnalyticsTab';

type TabKey =
  | 'leads' | 'pipeline' | 'customers' | 'followups' | 'forecast' | 'commlog'
  | 'contracts' | 'proposals' | 'quotes' | 'segments' | 'campaigns' | 'analytics';

const tabs: { key: TabKey; label: string; icon: typeof Users }[] = [
  { key: 'leads', label: 'Leads', icon: Target },
  { key: 'pipeline', label: 'Pipeline', icon: Workflow },
  { key: 'customers', label: 'Customers', icon: Users },
  { key: 'followups', label: 'Follow-ups', icon: Phone },
  { key: 'forecast', label: 'Forecast', icon: BarChart3 },
  { key: 'commlog', label: 'Comm log', icon: MessageSquare },
  { key: 'contracts', label: 'Contracts', icon: FileSignature },
  { key: 'proposals', label: 'Proposals', icon: FileText },
  { key: 'quotes', label: 'Quotes', icon: Receipt },
  { key: 'segments', label: 'Segments', icon: Layers },
  { key: 'campaigns', label: 'Campaigns', icon: Send },
  { key: 'analytics', label: 'Analytics', icon: BarChart3 },
];

export function CRMPage() {
  const [active, setActive] = useState<TabKey>('pipeline');
  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-brand-600">Module workspace</p>
        <h1 className="mt-1 flex items-center gap-2 text-3xl font-semibold">
          <Building2 className="text-brand-600" size={26} />
          CRM &amp; Sales
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-muted">
          12 offline CRM tools — leads, pipeline kanban, customers, follow-ups, forecast,
          communication log, contracts, proposals with PDF, quotes with PDF, customer segments,
          email campaigns, and analytics.
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
          {active === 'leads' && <LeadsTab />}
          {active === 'pipeline' && <PipelineTab />}
          {active === 'customers' && <CustomersTab />}
          {active === 'followups' && <FollowUpsTab />}
          {active === 'forecast' && <ForecastTab />}
          {active === 'commlog' && <CommLogTab />}
          {active === 'contracts' && <ContractsTab />}
          {active === 'proposals' && <ProposalsTab />}
          {active === 'quotes' && <QuotesTab />}
          {active === 'segments' && <SegmentsTab />}
          {active === 'campaigns' && <CampaignsTab />}
          {active === 'analytics' && <CRMAnalyticsTab />}
        </div>
      </div>
    </div>
  );
}
