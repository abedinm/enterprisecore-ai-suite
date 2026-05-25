import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ArrowLeft, Image as ImageIcon, Save, X } from 'lucide-react';
import { marketingApi, type ProjectInput } from '../../lib/marketing';
import { MediaPickerDialog } from './Media';

const EMPTY: ProjectInput = {
  title: '',
  client: '',
  category: '',
  summary: '',
  body: '',
  year: '',
  tags: [],
  featured: false,
  imageId: null,
  externalUrl: '',
};

export function MarketingPortfolioEditor() {
  const { projectId } = useParams<{ projectId?: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const isEdit = Boolean(projectId);

  const existing = useQuery({
    queryKey: ['marketing', 'project', projectId],
    queryFn: () => marketingApi.getProject(projectId!),
    enabled: isEdit,
  });

  const uploadsQ = useQuery({
    queryKey: ['marketing', 'uploads'],
    queryFn: () => marketingApi.listUploads(),
  });

  const [form, setForm] = useState<ProjectInput>(EMPTY);
  const [tagsStr, setTagsStr] = useState('');
  const [pickerOpen, setPickerOpen] = useState(false);

  useEffect(() => {
    if (existing.data) {
      const p = existing.data;
      setForm({
        title: p.title,
        client: p.client,
        category: p.category,
        summary: p.summary,
        body: p.body,
        year: p.year,
        tags: p.tags,
        featured: p.featured,
        imageId: p.imageId,
        externalUrl: p.externalUrl,
      });
      setTagsStr(p.tags.join(', '));
    }
  }, [existing.data]);

  const save = useMutation({
    mutationFn: async () => {
      const body: ProjectInput = {
        ...form,
        tags: tagsStr
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
      };
      if (isEdit && projectId) return marketingApi.updateProject(projectId, body);
      return marketingApi.createProject(body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'projects'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      if (projectId) qc.invalidateQueries({ queryKey: ['marketing', 'project', projectId] });
      toast.success(isEdit ? 'Project saved' : 'Project created');
      navigate('/marketing/portfolio');
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } }; message?: string })
        .response?.data?.detail ?? (err as Error).message ?? 'Failed to save';
      toast.error(typeof detail === 'string' ? detail : 'Failed to save');
    },
  });

  function update<K extends keyof ProjectInput>(key: K, value: ProjectInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  const heroImage =
    form.imageId && uploadsQ.data?.find((u) => u.id === form.imageId);

  if (isEdit && existing.isLoading) {
    return <p className="text-sm text-ink-muted">Loading project…</p>;
  }

  return (
    <div className="space-y-4">
      <div>
        <button
          type="button"
          className="ec-btn-ghost mb-2 !px-2 !py-1 text-xs"
          onClick={() => navigate('/marketing/portfolio')}
        >
          <ArrowLeft size={14} /> Back to portfolio
        </button>
        <h2 className="text-lg font-semibold">{isEdit ? 'Edit project' : 'New project'}</h2>
      </div>

      <form
        className="ec-card space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="ec-label">Title</label>
            <input
              className="ec-input"
              required
              value={form.title}
              onChange={(e) => update('title', e.target.value)}
            />
          </div>
          <div>
            <label className="ec-label">Client</label>
            <input
              className="ec-input"
              value={form.client}
              onChange={(e) => update('client', e.target.value)}
            />
          </div>
          <div>
            <label className="ec-label">Category</label>
            <input
              className="ec-input"
              value={form.category}
              onChange={(e) => update('category', e.target.value)}
              placeholder="Branding, Web, Product…"
            />
          </div>
          <div>
            <label className="ec-label">Year</label>
            <input
              className="ec-input"
              value={form.year}
              onChange={(e) => update('year', e.target.value)}
              placeholder="2025"
            />
          </div>
          <div className="md:col-span-2">
            <label className="ec-label">Tags (comma-separated)</label>
            <input
              className="ec-input"
              value={tagsStr}
              onChange={(e) => setTagsStr(e.target.value)}
              placeholder="branding, web, react"
            />
          </div>
          <div className="md:col-span-2">
            <label className="ec-label">Summary</label>
            <textarea
              className="ec-input min-h-[80px]"
              value={form.summary}
              onChange={(e) => update('summary', e.target.value)}
            />
          </div>
          <div className="md:col-span-2">
            <label className="ec-label">Body (markdown)</label>
            <textarea
              className="ec-input min-h-[200px] font-mono text-xs"
              value={form.body}
              onChange={(e) => update('body', e.target.value)}
            />
          </div>
          <div className="md:col-span-2">
            <label className="ec-label">External URL</label>
            <input
              className="ec-input font-mono"
              placeholder="https://…"
              value={form.externalUrl}
              onChange={(e) => update('externalUrl', e.target.value)}
            />
          </div>
        </div>

        <div className="border-t border-border pt-4">
          <label className="ec-label">Hero image</label>
          <div className="flex flex-wrap items-center gap-3">
            <div className="h-20 w-32 overflow-hidden rounded-lg border border-border bg-surface-muted">
              {heroImage ? (
                <img
                  src={heroImage.url}
                  alt={heroImage.filename}
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="grid h-full w-full place-items-center text-ink-subtle">
                  <ImageIcon size={20} />
                </div>
              )}
            </div>
            <button type="button" className="ec-btn-secondary" onClick={() => setPickerOpen(true)}>
              {heroImage ? 'Change image' : 'Pick image'}
            </button>
            {heroImage && (
              <button
                type="button"
                className="ec-btn-ghost text-rose-600"
                onClick={() => update('imageId', null)}
              >
                <X size={14} /> Clear
              </button>
            )}
          </div>
        </div>

        <div className="border-t border-border pt-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.featured}
              onChange={(e) => update('featured', e.target.checked)}
            />
            Featured — pin to the top of the portfolio grid
          </label>
        </div>

        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <button
            type="button"
            className="ec-btn-secondary"
            onClick={() => navigate('/marketing/portfolio')}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="ec-btn-primary"
            disabled={save.isPending || !form.title.trim()}
          >
            <Save size={16} /> {save.isPending ? 'Saving…' : isEdit ? 'Save project' : 'Create project'}
          </button>
        </div>
      </form>

      <MediaPickerDialog
        open={pickerOpen}
        selectedId={form.imageId}
        onClose={() => setPickerOpen(false)}
        onPick={(u) => update('imageId', u.id)}
      />
    </div>
  );
}
