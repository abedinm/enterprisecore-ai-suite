import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ExternalLink,
  FileText,
  HelpCircle,
  Image as ImageIcon,
  LayoutGrid,
  LayoutTemplate,
  ListChecks,
  MessageSquareQuote,
  Newspaper,
  Share2,
  Sparkles,
  Users,
} from 'lucide-react';
import { marketingApi } from '../../lib/marketing';

type CountTileProps = {
  to: string;
  label: string;
  icon: typeof ListChecks;
  value: number;
};

function CountTile({ to, label, icon: Icon, value }: CountTileProps) {
  return (
    <Link
      to={to}
      className="ec-card flex items-center justify-between p-4 transition hover:border-brand-500/40 hover:bg-surface-muted/30"
    >
      <div>
        <p className="text-xs uppercase tracking-wider text-ink-subtle">{label}</p>
        <p className="mt-1 text-2xl font-semibold">{value}</p>
      </div>
      <div className="grid h-10 w-10 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
        <Icon size={18} />
      </div>
    </Link>
  );
}

export function MarketingDashboard() {
  const stateQ = useQuery({
    queryKey: ['marketing', 'state'],
    queryFn: () => marketingApi.getState(),
  });

  const checklistQ = useQuery({
    queryKey: ['marketing', 'launch-checklist'],
    queryFn: () => marketingApi.getChecklist(),
  });

  if (stateQ.isLoading) {
    return <p className="text-sm text-ink-muted">Loading marketing state…</p>;
  }

  if (stateQ.isError || !stateQ.data) {
    return (
      <div className="ec-card border-rose-300 bg-rose-50 p-4 text-sm text-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
        <p className="font-semibold">Could not load marketing data</p>
        <p className="mt-1">
          Make sure your license includes the Marketing module and the API is reachable.
        </p>
      </div>
    );
  }

  const s = stateQ.data;
  const checklist = checklistQ.data ?? [];
  const done = checklist.filter((c) => c.complete).length;
  const total = checklist.length;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <div className="space-y-5">
      {pct < 50 && (
        <Link
          to="/marketing/templates"
          className="ec-card flex items-center gap-3 border-brand-500/40 bg-brand-600/5 p-4 text-sm transition hover:bg-brand-600/10"
        >
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-600/15 text-brand-600">
            <LayoutTemplate size={16} />
          </span>
          <span className="flex-1">
            <span className="font-semibold">New install?</span>{' '}
            <span className="text-ink-muted">
              Start from an industry template — pick a starting point that
              matches your business.
            </span>
          </span>
          <ArrowRight size={16} className="shrink-0 text-brand-600" />
        </Link>
      )}

      <div className="ec-card overflow-hidden">
        <div className="flex flex-wrap items-start justify-between gap-4 p-5">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wider text-ink-subtle">Site identity</p>
            <h2 className="mt-1 text-xl font-semibold">{s.settings.name || 'Untitled site'}</h2>
            {s.settings.tagline && (
              <p className="mt-1 text-sm text-ink-muted">{s.settings.tagline}</p>
            )}
            {s.settings.baseUrl && (
              <p className="mt-2 break-all text-xs text-ink-subtle">{s.settings.baseUrl}</p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <a
              href="/site/"
              target="_blank"
              rel="noopener noreferrer"
              className="ec-btn-primary"
            >
              <ExternalLink size={16} /> Preview site
            </a>
            <Link to="/marketing/settings" className="ec-btn-secondary">
              Edit identity
            </Link>
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <CountTile
            to="/marketing/pages"
            label="Sections"
            icon={LayoutGrid}
            value={s.sections.length}
          />
          <CountTile
            to="/marketing/portfolio"
            label="Projects"
            icon={Sparkles}
            value={s.projects.length}
          />
          <CountTile
            to="/marketing/blog"
            label="Posts"
            icon={Newspaper}
            value={s.posts.length}
          />
          <CountTile
            to="/marketing/services"
            label="Services"
            icon={FileText}
            value={s.services.length}
          />
          <CountTile
            to="/marketing/testimonials"
            label="Testimonials"
            icon={MessageSquareQuote}
            value={s.testimonials.length}
          />
          <CountTile
            to="/marketing/faqs"
            label="FAQs"
            icon={HelpCircle}
            value={s.faqs.length}
          />
          <CountTile
            to="/marketing/team"
            label="Team"
            icon={Users}
            value={s.team.length}
          />
          <CountTile
            to="/marketing/social"
            label="Social links"
            icon={Share2}
            value={s.social_links.length}
          />
          <CountTile
            to="/marketing/media"
            label="Media"
            icon={ImageIcon}
            value={0}
          />
        </div>

        <div className="ec-card flex flex-col p-5">
          <div className="flex items-center justify-between">
            <p className="flex items-center gap-2 font-semibold">
              <ListChecks size={16} className="text-brand-600" />
              Launch checklist
            </p>
            <span className="text-xs text-ink-muted">{done}/{total}</span>
          </div>
          <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-surface-muted">
            <div
              className="h-full rounded-full bg-brand-600 transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-ink-subtle">{pct}% complete</p>

          <ul className="mt-4 space-y-2">
            {checklistQ.isLoading && (
              <li className="text-sm text-ink-muted">Loading…</li>
            )}
            {checklist.length === 0 && !checklistQ.isLoading && (
              <li className="text-sm text-ink-muted">No checklist items.</li>
            )}
            {checklist.map((item) => (
              <li key={item.id} className="flex items-start gap-2 text-sm">
                {item.complete ? (
                  <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-600" />
                ) : (
                  <AlertCircle size={16} className="mt-0.5 shrink-0 text-amber-500" />
                )}
                <span className={item.complete ? 'text-ink-muted line-through' : 'text-ink'}>
                  {item.label}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
