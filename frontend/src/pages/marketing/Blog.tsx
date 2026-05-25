import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Edit3, FileText, Plus, Trash2 } from 'lucide-react';
import { marketingApi, type MarketingPost } from '../../lib/marketing';
import { formatDate } from '../../lib/utils';

export function MarketingBlogPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const postsQ = useQuery({
    queryKey: ['marketing', 'posts'],
    queryFn: () => marketingApi.listPosts(),
  });

  const remove = useMutation({
    mutationFn: (id: string) => marketingApi.deletePost(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'posts'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      toast.success('Post deleted');
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Blog</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Posts shown on /blog and individual /blog/&lt;slug&gt; pages.
          </p>
        </div>
        <button
          type="button"
          className="ec-btn-primary"
          onClick={() => navigate('/marketing/blog/new')}
        >
          <Plus size={16} /> New post
        </button>
      </div>

      {postsQ.isLoading && <p className="text-sm text-ink-muted">Loading posts…</p>}

      {postsQ.data && postsQ.data.length === 0 && (
        <div className="grid place-items-center rounded-xl border border-dashed border-border bg-surface-muted/40 p-10 text-center">
          <FileText size={28} className="mb-3 text-ink-subtle" />
          <p className="font-semibold">No posts yet</p>
          <p className="mt-1 text-sm text-ink-muted">
            Write your first blog post to populate the public blog page.
          </p>
          <button
            className="ec-btn-primary mt-4"
            onClick={() => navigate('/marketing/blog/new')}
          >
            <Plus size={16} /> New post
          </button>
        </div>
      )}

      {postsQ.data && postsQ.data.length > 0 && (
        <div className="ec-card overflow-hidden">
          <table className="ec-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Status</th>
                <th>Author</th>
                <th>Published</th>
                <th className="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {postsQ.data.map((p) => (
                <PostRow
                  key={p.id}
                  post={p}
                  onDelete={() => {
                    if (confirm(`Delete post "${p.title}"?`)) remove.mutate(p.id);
                  }}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function PostRow({
  post,
  onDelete,
}: {
  post: MarketingPost;
  onDelete: () => void;
}) {
  return (
    <tr className="hover:bg-surface-muted/40">
      <td>
        <Link to={`/marketing/blog/${post.id}`} className="block">
          <span className="block font-medium hover:text-brand-600">{post.title}</span>
          {post.slug && (
            <span className="block font-mono text-xs text-ink-subtle">/{post.slug}</span>
          )}
        </Link>
      </td>
      <td>
        {post.status === 'published' ? (
          <span className="ec-badge-green">Published</span>
        ) : (
          <span className="ec-badge bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200">
            Draft
          </span>
        )}
      </td>
      <td className="text-ink-muted">{post.author || '—'}</td>
      <td className="text-ink-muted">{post.publishDate ? formatDate(post.publishDate) : '—'}</td>
      <td className="text-right">
        <div className="inline-flex gap-1">
          <Link
            to={`/marketing/blog/${post.id}`}
            className="ec-btn-ghost !py-1.5 !px-2.5 text-xs"
            title="Edit"
          >
            <Edit3 size={13} />
          </Link>
          <button
            type="button"
            className="ec-btn-ghost !py-1.5 !px-2.5 text-xs text-rose-600"
            onClick={onDelete}
            title="Delete"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </td>
    </tr>
  );
}
