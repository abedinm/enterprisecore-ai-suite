import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Eye, FileUp, Sparkles, X } from 'lucide-react';
import {
  marketingApi,
  sectionTypeLabel,
  type MarketingTemplate,
  type MarketingTemplateSummary,
} from '../../lib/marketing';

export function MarketingTemplatesPage() {
  const listQ = useQuery({
    queryKey: ['marketing', 'templates'],
    queryFn: () => marketingApi.listTemplates(),
  });

  const [previewing, setPreviewing] = useState<MarketingTemplateSummary | null>(null);
  const [applying, setApplying] = useState<MarketingTemplateSummary | null>(null);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Industry templates</h2>
          <p className="mt-1 max-w-3xl text-sm text-ink-muted">
            Start your site from a working template designed for your industry.
            You can edit everything afterward.
          </p>
        </div>
        <SiteForgeImportButton />
      </div>

      {listQ.isLoading && (
        <p className="text-sm text-ink-muted">Loading templates…</p>
      )}

      {listQ.isError && (
        <div className="ec-card border-rose-300 bg-rose-50 p-4 text-sm text-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
          <p className="font-semibold">Could not load templates</p>
          <p className="mt-1">
            Make sure the marketing API is reachable and templates are seeded.
          </p>
        </div>
      )}

      {listQ.data && listQ.data.length === 0 && (
        <p className="ec-card p-6 text-center text-sm text-ink-muted">
          No templates are available yet.
        </p>
      )}

      {listQ.data && listQ.data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {listQ.data.map((tpl) => (
            <article
              key={tpl.id}
              className="ec-card flex flex-col overflow-hidden"
            >
              {tpl.preview_image ? (
                <div className="aspect-video w-full overflow-hidden bg-surface-muted">
                  <img
                    src={tpl.preview_image}
                    alt={`${tpl.name} preview`}
                    className="h-full w-full object-cover"
                  />
                </div>
              ) : (
                <div className="grid aspect-video w-full place-items-center bg-gradient-to-br from-brand-600/15 to-brand-600/5 text-brand-600">
                  <Sparkles size={36} />
                </div>
              )}
              <div className="flex flex-1 flex-col gap-3 p-4">
                <div>
                  <h3 className="text-base font-semibold">{tpl.name}</h3>
                  <p className="mt-1 text-sm text-ink-muted">{tpl.description}</p>
                </div>
                <div className="mt-auto flex flex-wrap gap-2 pt-2">
                  <button
                    type="button"
                    className="ec-btn-secondary"
                    onClick={() => setPreviewing(tpl)}
                  >
                    <Eye size={14} /> Preview
                  </button>
                  <button
                    type="button"
                    className="ec-btn-primary"
                    onClick={() => setApplying(tpl)}
                  >
                    Use this template
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}

      {previewing && (
        <TemplatePreviewModal
          summary={previewing}
          onClose={() => setPreviewing(null)}
          onApply={() => {
            const next = previewing;
            setPreviewing(null);
            setApplying(next);
          }}
        />
      )}

      {applying && (
        <TemplateApplyDialog
          template={applying}
          onClose={() => setApplying(null)}
        />
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  SiteForge JSON import — file picker → POST /import-siteforge → toast       */
/* -------------------------------------------------------------------------- */

function SiteForgeImportButton() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const importMutation = useMutation({
    mutationFn: (file: File) => marketingApi.importSiteforge(file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing'] });
      toast.success('Imported from SiteForge — existing content was replaced.');
      navigate('/marketing');
    },
    onError: (err: unknown) => {
      const status = (err as { response?: { status?: number } }).response?.status;
      if (status === 403) {
        toast.error('Only admins or managers can import.');
        return;
      }
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
        (err as Error).message ??
        'SiteForge import failed';
      toast.error(typeof detail === 'string' ? detail : 'SiteForge import failed');
    },
  });

  function onPick(file: File | null | undefined) {
    if (!file) return;
    importMutation.mutate(file);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  return (
    <div className="flex items-start gap-2">
      <button
        type="button"
        className="ec-btn-secondary"
        disabled={importMutation.isPending}
        onClick={() => fileInputRef.current?.click()}
      >
        <FileUp size={14} />
        {importMutation.isPending ? 'Importing…' : 'Import from SiteForge JSON'}
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept="application/json,.json"
        className="hidden"
        onChange={(e) => onPick(e.target.files?.[0])}
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Preview modal — read-only summary of what's in the template.               */
/* -------------------------------------------------------------------------- */

type PreviewProps = {
  summary: MarketingTemplateSummary;
  onClose: () => void;
  onApply: () => void;
};

function TemplatePreviewModal({ summary, onClose, onApply }: PreviewProps) {
  const detailQ = useQuery({
    queryKey: ['marketing', 'templates', summary.id],
    queryFn: () => marketingApi.getTemplate(summary.id),
  });

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="flex w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-ink-subtle">
              Template preview
            </p>
            <p className="font-semibold">{summary.name}</p>
          </div>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div className="max-h-[70vh] space-y-4 overflow-y-auto p-5">
          {detailQ.isLoading && (
            <p className="text-sm text-ink-muted">Loading template details…</p>
          )}

          {detailQ.isError && (
            <p className="text-sm text-rose-600">
              Could not load template details.
            </p>
          )}

          {detailQ.data && <TemplatePreviewBody template={detailQ.data} />}
        </div>

        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" className="ec-btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="ec-btn-primary"
            disabled={detailQ.isLoading}
            onClick={onApply}
          >
            Use this template
          </button>
        </div>
      </div>
    </div>
  );
}

function TemplatePreviewBody({ template }: { template: MarketingTemplate }) {
  const sections = [...(template.sections ?? [])].sort(
    (a, b) => a.order - b.order,
  );

  return (
    <div className="space-y-5">
      <section>
        <p className="text-xs uppercase tracking-wider text-ink-subtle">
          Settings
        </p>
        <div className="mt-2 space-y-1 text-sm">
          <p>
            <span className="text-ink-muted">Site name:</span>{' '}
            <span className="font-medium">{template.settings?.name || '—'}</span>
          </p>
          {template.settings?.tagline && (
            <p>
              <span className="text-ink-muted">Tagline:</span>{' '}
              <span>{template.settings.tagline}</span>
            </p>
          )}
          <div className="flex items-center gap-2 pt-1">
            <span className="text-xs text-ink-muted">Colors:</span>
            {template.settings?.primaryColor && (
              <span className="flex items-center gap-1.5 text-xs">
                <span
                  className="inline-block h-4 w-4 rounded border border-border"
                  style={{ background: template.settings.primaryColor }}
                />
                {template.settings.primaryColor}
              </span>
            )}
            {template.settings?.accentColor && (
              <span className="flex items-center gap-1.5 text-xs">
                <span
                  className="inline-block h-4 w-4 rounded border border-border"
                  style={{ background: template.settings.accentColor }}
                />
                {template.settings.accentColor}
              </span>
            )}
          </div>
        </div>
      </section>

      <section>
        <p className="text-xs uppercase tracking-wider text-ink-subtle">
          Sections ({sections.length})
        </p>
        {sections.length === 0 ? (
          <p className="mt-2 text-sm text-ink-muted">No sections.</p>
        ) : (
          <ul className="mt-2 space-y-1.5">
            {sections.map((s) => (
              <li
                key={s.id || `${s.type}-${s.order}`}
                className="flex items-center gap-2 text-sm"
              >
                <span className="ec-badge bg-brand-600/15 text-brand-600">
                  {sectionTypeLabel(s.type)}
                </span>
                <span className="truncate">
                  {s.title || (
                    <span className="italic text-ink-muted">Untitled</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <p className="text-xs uppercase tracking-wider text-ink-subtle">
          Content
        </p>
        <div className="mt-2 grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
          <CountRow label="Projects" value={template.projects?.length ?? 0} />
          <CountRow label="Posts" value={template.posts?.length ?? 0} />
          <CountRow label="Services" value={template.services?.length ?? 0} />
          <CountRow
            label="Testimonials"
            value={template.testimonials?.length ?? 0}
          />
          <CountRow label="FAQs" value={template.faqs?.length ?? 0} />
          <CountRow label="Team members" value={template.team?.length ?? 0} />
          <CountRow
            label="Social links"
            value={template.social_links?.length ?? 0}
          />
        </div>
      </section>
    </div>
  );
}

function CountRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="ec-card flex items-center justify-between p-2.5">
      <span className="text-xs text-ink-muted">{label}</span>
      <span className="text-sm font-semibold">{value}</span>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Apply confirm dialog — REPLACES or APPENDS template content.               */
/* -------------------------------------------------------------------------- */

type ApplyProps = {
  template: MarketingTemplateSummary;
  onClose: () => void;
};

function TemplateApplyDialog({ template, onClose }: ApplyProps) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [wipeExisting, setWipeExisting] = useState(true);

  const apply = useMutation({
    mutationFn: () =>
      marketingApi.useTemplate(template.id, { wipe_existing: wipeExisting }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing'] });
      toast.success(`Applied template: ${template.name}`);
      onClose();
      navigate('/marketing');
    },
    onError: (err: unknown) => {
      const status = (err as { response?: { status?: number } }).response?.status;
      if (status === 403) {
        toast.error('Only admins or managers can apply templates.');
        return;
      }
      const detail = (err as {
        response?: { data?: { detail?: string } };
        message?: string;
      }).response?.data?.detail ?? (err as Error).message ?? 'Failed to apply template';
      toast.error(typeof detail === 'string' ? detail : 'Failed to apply template');
    },
  });

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !apply.isPending) onClose();
      }}
    >
      <div className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-ink-subtle">
              Apply template
            </p>
            <p className="font-semibold">{template.name}</p>
          </div>
          <button
            type="button"
            className="ec-btn-ghost !p-2"
            onClick={onClose}
            disabled={apply.isPending}
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-3 p-5 text-sm">
          {wipeExisting ? (
            <p className="font-semibold text-rose-600">
              This will REPLACE all of your current marketing content
              (sections, projects, posts, services, testimonials, FAQs, team,
              social links) with the template's content.
            </p>
          ) : (
            <p className="font-semibold">
              The template's content will be APPENDED to your existing
              marketing content (nothing will be removed).
            </p>
          )}
          <p className="text-ink-muted">
            Your uploaded media will NOT be affected.
          </p>

          <label className="mt-2 flex items-start gap-2 rounded-md border border-border bg-surface-muted/40 p-3">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={wipeExisting}
              onChange={(e) => setWipeExisting(e.target.checked)}
              disabled={apply.isPending}
            />
            <span>
              <span className="font-medium">Wipe existing content</span>
              <span className="block text-xs text-ink-muted">
                When OFF, template content is appended instead of replacing.
              </span>
            </span>
          </label>
        </div>

        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <button
            type="button"
            className="ec-btn-secondary"
            onClick={onClose}
            disabled={apply.isPending}
          >
            Cancel
          </button>
          <button
            type="button"
            className="ec-btn-primary"
            disabled={apply.isPending}
            onClick={() => apply.mutate()}
          >
            {apply.isPending ? 'Applying…' : 'Apply template'}
          </button>
        </div>
      </div>
    </div>
  );
}
