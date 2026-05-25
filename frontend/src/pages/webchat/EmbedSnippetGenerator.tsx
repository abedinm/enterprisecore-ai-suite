import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Check, Code2, Copy } from 'lucide-react';
import toast from 'react-hot-toast';
import { webchatApi } from '../../lib/webchat';

export function EmbedSnippetGenerator() {
  const { botId } = useParams<{ botId: string }>();
  const [copied, setCopied] = useState(false);

  const bot = useQuery({
    queryKey: ['webchat', 'bot', botId],
    queryFn: () => webchatApi.getBot(botId!),
    enabled: Boolean(botId),
  });

  async function copySnippet() {
    if (!bot.data?.embed_snippet) return;
    try {
      await navigator.clipboard.writeText(bot.data.embed_snippet);
      setCopied(true);
      toast.success('Snippet copied to clipboard');
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error('Clipboard blocked — copy manually from the snippet below.');
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <Link to="/webchat" className="ec-btn-ghost mb-2 !px-2 !py-1 text-xs">
          <ArrowLeft size={14} /> Back to bots
        </Link>
        <h1 className="flex items-center gap-2 text-2xl font-semibold sm:text-3xl">
          <Code2 className="text-brand-600" size={24} />
          Embed snippet
          {bot.data && <span className="text-ink-muted font-normal">· {bot.data.name}</span>}
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-muted">
          Paste this snippet anywhere in your site's HTML — usually just before
          the closing <code className="rounded bg-surface-muted px-1 py-0.5 text-xs">&lt;/body&gt;</code>{' '}
          tag. The widget loads asynchronously and won't block your page.
        </p>
      </div>

      {bot.isLoading && <p className="text-sm text-ink-muted">Loading bot…</p>}

      {bot.data && (
        <>
          <div className="ec-card overflow-hidden">
            <div className="flex items-center justify-between border-b border-border bg-surface-muted px-4 py-2">
              <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">
                Snippet
              </p>
              <button
                type="button"
                className="ec-btn-primary !py-1.5 !px-3 text-xs"
                onClick={copySnippet}
              >
                {copied ? <Check size={13} /> : <Copy size={13} />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
            <pre className="overflow-x-auto p-4 text-xs leading-relaxed text-ink">
{bot.data.embed_snippet}
            </pre>
          </div>

          <div className="ec-card p-5">
            <p className="text-sm font-semibold">How to embed</p>
            <ol className="mt-3 space-y-2 text-sm text-ink-muted">
              <li>1. Copy the snippet above.</li>
              <li>2. Paste it into the HTML of any page where you want the
                chat to appear — typically just before the closing
                {' '}<code className="rounded bg-surface-muted px-1 py-0.5 text-xs">&lt;/body&gt;</code>{' '}
                tag.</li>
              <li>3. Save and reload the page. The chat button appears in the
                bottom-right corner.</li>
            </ol>
            <p className="mt-3 text-xs text-ink-subtle">
              The widget loads with <code className="rounded bg-surface-muted px-1 py-0.5">defer</code>,
              so it won't slow down your initial render. It only sends messages
              while this bot's <em>Public</em> toggle is on.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
