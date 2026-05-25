import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ArrowLeft, RefreshCw, Save } from 'lucide-react';
import { marketingApi, slugify, type PostInput } from '../../lib/marketing';

const EMPTY: PostInput = {
  title: '',
  slug: '',
  excerpt: '',
  body: '',
  author: '',
  category: '',
  tags: [],
  publishDate: '',
  status: 'draft',
  seoTitle: '',
  seoDescription: '',
};

function isoDateInput(value: string): string {
  if (!value) return '';
  // Accept both ISO and YYYY-MM-DD shapes. <input type="date"> wants YYYY-MM-DD.
  try {
    return new Date(value).toISOString().slice(0, 10);
  } catch {
    return '';
  }
}

export function MarketingBlogEditor() {
  const { postId } = useParams<{ postId?: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const isEdit = Boolean(postId);

  const existing = useQuery({
    queryKey: ['marketing', 'post', postId],
    queryFn: () => marketingApi.getPost(postId!),
    enabled: isEdit,
  });

  const [form, setForm] = useState<PostInput>(EMPTY);
  const [tagsStr, setTagsStr] = useState('');
  const [slugTouched, setSlugTouched] = useState(false);

  useEffect(() => {
    if (existing.data) {
      const p = existing.data;
      setForm({
        title: p.title,
        slug: p.slug,
        excerpt: p.excerpt,
        body: p.body,
        author: p.author,
        category: p.category,
        tags: p.tags,
        publishDate: p.publishDate,
        status: p.status,
        seoTitle: p.seoTitle,
        seoDescription: p.seoDescription,
      });
      setTagsStr(p.tags.join(', '));
      setSlugTouched(Boolean(p.slug));
    }
  }, [existing.data]);

  // Auto-derive slug from title until the user manually edits it.
  useEffect(() => {
    if (!slugTouched) {
      setForm((f) => ({ ...f, slug: slugify(f.title) }));
    }
  }, [form.title, slugTouched]);

  const save = useMutation({
    mutationFn: async () => {
      const body: PostInput = {
        ...form,
        tags: tagsStr
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
        publishDate: form.publishDate
          ? new Date(form.publishDate).toISOString()
          : '',
      };
      if (isEdit && postId) return marketingApi.updatePost(postId, body);
      return marketingApi.createPost(body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'posts'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      if (postId) qc.invalidateQueries({ queryKey: ['marketing', 'post', postId] });
      toast.success(isEdit ? 'Post saved' : 'Post created');
      navigate('/marketing/blog');
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } }; message?: string })
        .response?.data?.detail ?? (err as Error).message ?? 'Failed to save';
      toast.error(typeof detail === 'string' ? detail : 'Failed to save');
    },
  });

  function update<K extends keyof PostInput>(key: K, value: PostInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  if (isEdit && existing.isLoading) {
    return <p className="text-sm text-ink-muted">Loading post…</p>;
  }

  return (
    <div className="space-y-4">
      <div>
        <button
          type="button"
          className="ec-btn-ghost mb-2 !px-2 !py-1 text-xs"
          onClick={() => navigate('/marketing/blog')}
        >
          <ArrowLeft size={14} /> Back to blog
        </button>
        <h2 className="text-lg font-semibold">{isEdit ? 'Edit post' : 'New post'}</h2>
      </div>

      <form
        className="ec-card space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="grid gap-4 md:grid-cols-[1fr_auto]">
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
            <label className="ec-label">Status</label>
            <div className="flex h-10 items-center gap-2">
              <label className="flex cursor-pointer items-center gap-1.5 text-sm">
                <input
                  type="radio"
                  name="status"
                  checked={form.status === 'draft'}
                  onChange={() => update('status', 'draft')}
                />
                Draft
              </label>
              <label className="flex cursor-pointer items-center gap-1.5 text-sm">
                <input
                  type="radio"
                  name="status"
                  checked={form.status === 'published'}
                  onChange={() => update('status', 'published')}
                />
                Published
              </label>
            </div>
          </div>
        </div>

        <div>
          <label className="ec-label">Slug</label>
          <div className="flex gap-2">
            <input
              className="ec-input font-mono"
              value={form.slug}
              onChange={(e) => {
                setSlugTouched(true);
                update('slug', e.target.value);
              }}
              placeholder="auto-derived from title"
            />
            <button
              type="button"
              className="ec-btn-secondary"
              title="Reset to auto-derive"
              onClick={() => {
                setSlugTouched(false);
                update('slug', slugify(form.title));
              }}
            >
              <RefreshCw size={14} />
            </button>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <label className="ec-label">Author</label>
            <input
              className="ec-input"
              value={form.author}
              onChange={(e) => update('author', e.target.value)}
            />
          </div>
          <div>
            <label className="ec-label">Category</label>
            <input
              className="ec-input"
              value={form.category}
              onChange={(e) => update('category', e.target.value)}
            />
          </div>
          <div>
            <label className="ec-label">Publish date</label>
            <input
              type="date"
              className="ec-input"
              value={isoDateInput(form.publishDate)}
              onChange={(e) => update('publishDate', e.target.value)}
            />
          </div>
        </div>

        <div>
          <label className="ec-label">Tags (comma-separated)</label>
          <input
            className="ec-input"
            value={tagsStr}
            onChange={(e) => setTagsStr(e.target.value)}
          />
        </div>

        <div>
          <label className="ec-label">Excerpt</label>
          <textarea
            className="ec-input min-h-[80px]"
            value={form.excerpt}
            onChange={(e) => update('excerpt', e.target.value)}
          />
        </div>

        <div>
          <label className="ec-label">Body (markdown)</label>
          <textarea
            className="ec-input min-h-[320px] font-mono text-xs"
            value={form.body}
            onChange={(e) => update('body', e.target.value)}
          />
        </div>

        <div className="border-t border-border pt-4">
          <p className="text-sm font-semibold">SEO overrides</p>
          <p className="mt-1 text-xs text-ink-muted">
            Optional — leave blank to use site defaults.
          </p>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <div>
              <label className="ec-label">SEO title</label>
              <input
                className="ec-input"
                value={form.seoTitle}
                onChange={(e) => update('seoTitle', e.target.value)}
              />
            </div>
            <div>
              <label className="ec-label">SEO description</label>
              <input
                className="ec-input"
                value={form.seoDescription}
                onChange={(e) => update('seoDescription', e.target.value)}
              />
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <button
            type="button"
            className="ec-btn-secondary"
            onClick={() => navigate('/marketing/blog')}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="ec-btn-primary"
            disabled={save.isPending || !form.title.trim()}
          >
            <Save size={16} /> {save.isPending ? 'Saving…' : isEdit ? 'Save post' : 'Create post'}
          </button>
        </div>
      </form>
    </div>
  );
}
