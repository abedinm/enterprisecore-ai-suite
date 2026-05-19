import { useQuery } from '@tanstack/react-query';
import { ClipboardCheck } from 'lucide-react';
import { api } from '../../lib/api';

type Checklist = {
  framework: string;
  items: { id: string; item: string; category: string }[];
};

export function GDPRTab() {
  const { data } = useQuery({
    queryKey: ['security', 'gdpr'],
    queryFn: async () => (await api.get<Checklist>('/security/gdpr/checklist')).data,
  });

  if (!data) return <p className="text-sm text-ink-muted">Loading…</p>;

  const byCategory: Record<string, typeof data.items> = {};
  for (const item of data.items) {
    (byCategory[item.category] ||= []).push(item);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <ClipboardCheck className="text-brand-600" size={20} />
        <div>
          <p className="font-semibold">{data.framework} compliance checklist</p>
          <p className="text-xs text-ink-muted">{data.items.length} controls across {Object.keys(byCategory).length} categories</p>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {Object.entries(byCategory).map(([cat, items]) => (
          <div key={cat} className="ec-card p-4">
            <p className="mb-2 text-xs uppercase tracking-wider text-ink-muted">{cat}</p>
            <ul className="space-y-2 text-sm">
              {items.map((i) => (
                <li key={i.id} className="flex items-start gap-2">
                  <span className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full bg-brand-500" />
                  <span><strong className="text-xs uppercase tracking-wide text-brand-600">{i.id}</strong> · {i.item}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
