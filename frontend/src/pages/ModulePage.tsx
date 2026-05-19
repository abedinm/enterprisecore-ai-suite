import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { Hammer } from 'lucide-react';
import { api, type ModuleGroup } from '../lib/api';

const MAP: Record<string, { title: string; group: string; description: string }> = {
  finance: { title: 'Finance & Accounting', group: 'Finance', description: 'Invoices, expenses, payroll, budgets, tax, reports.' },
  hr: { title: 'HR & People Management', group: 'HR', description: 'Employees, attendance, leave, reviews, recruitment, payslips.' },
  crm: { title: 'CRM & Sales', group: 'CRM', description: 'Leads, pipeline, customers, contracts, proposals, campaigns.' },
  projects: { title: 'Project Management', group: 'Projects', description: 'Kanban, Gantt, sprints, tasks, meetings, time tracking.' },
  inventory: { title: 'Inventory & Supply Chain', group: 'Inventory', description: 'Stock, purchase orders, suppliers, warehouses, shipments.' },
  documents: { title: 'Document Management', group: 'Documents', description: 'Editor, PDF, e-sign, templates, versions, sharing.' },
  communication: { title: 'Communication & Collaboration', group: 'Communication', description: 'Messages, announcements, calendar, notes, polls, wiki.' },
  wiki: { title: 'Wiki', group: 'Communication', description: 'Internal knowledge base.' },
  security: { title: 'Security & Compliance', group: 'Security', description: 'Access control, audit logs, password vault, backups, compliance.' },
  coding: { title: 'AI Coding Assistant', group: 'AI Coding', description: 'Editor, terminal, chat, generation, review, multi-file, Git, API tester.' },
  ai: { title: 'AI Brain', group: 'AI Brain', description: 'Writer, summaries, narrators, forecasting, chatbots, sentiment, Ollama.' },
};

export function ModulePage() {
  const { module = 'finance' } = useParams();
  const info = MAP[module] ?? { title: module, group: module, description: '' };

  const { data } = useQuery({
    queryKey: ['modules'],
    queryFn: async () => (await api.get<{ groups: ModuleGroup[] }>('/modules')).data,
  });
  const group = data?.groups.find((g) => g.group.toLowerCase() === info.group.toLowerCase());

  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-brand-600">Module workspace</p>
        <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">{info.title}</h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-muted">{info.description}</p>
      </div>
      <div className="ec-card flex flex-wrap items-center gap-3 p-4 text-sm text-ink-muted">
        <Hammer size={16} />
        Foundation reserved this module's database tables, schemas, and route. The feature screens will plug in here as each module rolls out.
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {(group?.items ?? []).map((item) => (
          <div key={item} className="ec-card p-5">
            <p className="font-medium">{item}</p>
            <p className="mt-1 text-xs text-ink-muted">Database-backed and ready for implementation.</p>
          </div>
        ))}
      </div>
    </div>
  );
}
