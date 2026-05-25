import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Edit3, ExternalLink, Plus, Star, Trash2 } from 'lucide-react';
import { marketingApi, type MarketingProject } from '../../lib/marketing';

export function MarketingPortfolioPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const projectsQ = useQuery({
    queryKey: ['marketing', 'projects'],
    queryFn: () => marketingApi.listProjects(),
  });

  const remove = useMutation({
    mutationFn: (id: string) => marketingApi.deleteProject(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'projects'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      toast.success('Project deleted');
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Portfolio</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Case studies and project entries shown on /portfolio and the home page.
          </p>
        </div>
        <button
          type="button"
          className="ec-btn-primary"
          onClick={() => navigate('/marketing/portfolio/new')}
        >
          <Plus size={16} /> New project
        </button>
      </div>

      {projectsQ.isLoading && <p className="text-sm text-ink-muted">Loading projects…</p>}

      {projectsQ.data && projectsQ.data.length === 0 && (
        <div className="grid place-items-center rounded-xl border border-dashed border-border bg-surface-muted/40 p-10 text-center">
          <Star size={28} className="mb-3 text-ink-subtle" />
          <p className="font-semibold">No projects yet</p>
          <p className="mt-1 text-sm text-ink-muted">
            Add your first case study to populate the portfolio grid.
          </p>
          <button
            className="ec-btn-primary mt-4"
            onClick={() => navigate('/marketing/portfolio/new')}
          >
            <Plus size={16} /> New project
          </button>
        </div>
      )}

      {projectsQ.data && projectsQ.data.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {projectsQ.data.map((p) => (
            <ProjectCard
              key={p.id}
              project={p}
              onDelete={() => {
                if (confirm(`Delete project "${p.title}"?`)) remove.mutate(p.id);
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ProjectCard({
  project,
  onDelete,
}: {
  project: MarketingProject;
  onDelete: () => void;
}) {
  return (
    <div className="ec-card flex h-full flex-col p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {project.featured && (
              <span className="ec-badge-amber inline-flex items-center gap-1">
                <Star size={11} /> Featured
              </span>
            )}
            {project.category && (
              <span className="ec-badge bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200">
                {project.category}
              </span>
            )}
          </div>
          <p className="mt-1.5 truncate text-base font-semibold">{project.title}</p>
          {project.client && (
            <p className="text-xs text-ink-muted">for {project.client}</p>
          )}
          {project.summary && (
            <p className="mt-2 line-clamp-3 text-xs text-ink-muted">{project.summary}</p>
          )}
        </div>
      </div>

      {project.tags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {project.tags.slice(0, 5).map((t) => (
            <span key={t} className="ec-badge bg-brand-600/10 text-brand-600">
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-1.5">
        <Link
          to={`/marketing/portfolio/${project.id}`}
          className="ec-btn-secondary !py-1.5 !px-2.5 text-xs"
        >
          <Edit3 size={13} /> Edit
        </Link>
        {project.externalUrl && (
          <a
            href={project.externalUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="ec-btn-ghost !py-1.5 !px-2.5 text-xs"
          >
            <ExternalLink size={13} /> Visit
          </a>
        )}
        <button
          type="button"
          className="ec-btn-ghost !py-1.5 !px-2.5 text-xs text-rose-600"
          onClick={onDelete}
        >
          <Trash2 size={13} />
        </button>
      </div>
    </div>
  );
}
