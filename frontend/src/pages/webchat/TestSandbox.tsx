import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, PlayCircle, RefreshCcw } from 'lucide-react';
import { API_BASE } from '../../lib/api';
import { webchatApi } from '../../lib/webchat';

/** API_BASE ends in /api/v1; the widget script lives at the same origin's root. */
function widgetOrigin(): string {
  try {
    const u = new URL(API_BASE, window.location.origin);
    return `${u.protocol}//${u.host}`;
  } catch {
    return window.location.origin;
  }
}

function buildSandboxHtml(botId: string): string {
  const origin = widgetOrigin();
  // The script's data-bot-id attribute is what the backend snippet uses.
  // Run inside an isolated iframe so it can't touch the dashboard's DOM.
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Web Chat sandbox</title>
<style>
  html, body { height: 100%; margin: 0; }
  body {
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    background: linear-gradient(180deg, #f7f8fb 0%, #eef1f6 100%);
    color: #1f2937;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    box-sizing: border-box;
  }
  .card {
    max-width: 420px;
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    padding: 22px 22px 18px;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
  }
  h1 { font-size: 17px; margin: 0 0 6px; }
  p  { font-size: 13px; line-height: 1.5; color: #4b5563; margin: 0; }
  .tag {
    display: inline-block;
    margin-bottom: 10px;
    padding: 2px 8px;
    font-size: 11px;
    border-radius: 999px;
    background: #eef2ff;
    color: #4338ca;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    font-weight: 600;
  }
</style>
</head>
<body>
  <div class="card">
    <span class="tag">Sandbox preview</span>
    <h1>This is a blank page</h1>
    <p>The chat widget script has been injected. Look for the chat button in
    the bottom-right corner — it sends real messages to your bot exactly the
    way visitors will see it on your site.</p>
  </div>
  <script src="${origin}/widget.js" data-bot-id="${botId}" defer></script>
</body>
</html>`;
}

export function TestSandbox() {
  const { botId } = useParams<{ botId: string }>();
  const [nonce, setNonce] = useState(0);
  const objectUrlRef = useRef<string | null>(null);

  const bot = useQuery({
    queryKey: ['webchat', 'bot', botId],
    queryFn: () => webchatApi.getBot(botId!),
    enabled: Boolean(botId),
  });

  const blobUrl = useMemo(() => {
    if (!botId) return null;
    const html = buildSandboxHtml(botId);
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    objectUrlRef.current = url;
    return url;
    // nonce intentionally invalidates the memo to force a reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [botId, nonce]);

  useEffect(() => () => {
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
  }, []);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link to="/webchat" className="ec-btn-ghost mb-2 !px-2 !py-1 text-xs">
            <ArrowLeft size={14} /> Back to bots
          </Link>
          <h1 className="flex items-center gap-2 text-2xl font-semibold sm:text-3xl">
            <PlayCircle className="text-brand-600" size={24} />
            Sandbox
            {bot.data && <span className="text-ink-muted font-normal">· {bot.data.name}</span>}
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-muted">
            Try the widget — it sends real messages to your bot. Use this to
            confirm the persona, language detection, and rate limiting before
            you embed the snippet on a live site.
          </p>
        </div>
        <button
          type="button"
          className="ec-btn-secondary"
          onClick={() => setNonce((n) => n + 1)}
        >
          <RefreshCcw size={14} /> Reload widget
        </button>
      </div>

      <div className="ec-card overflow-hidden">
        {blobUrl ? (
          <iframe
            key={`sandbox-${nonce}`}
            title="Web Chat sandbox"
            src={blobUrl}
            sandbox="allow-scripts allow-forms allow-same-origin"
            className="block w-full"
            style={{ height: '70vh', minHeight: 480, border: 0 }}
          />
        ) : (
          <p className="p-6 text-sm text-ink-muted">Preparing sandbox…</p>
        )}
      </div>

      <p className="text-xs text-ink-subtle">
        The sandbox loads a blank page and injects <code className="rounded bg-surface-muted px-1 py-0.5">/widget.js</code>{' '}
        with this bot's id. Messages sent here count against the bot's rate
        limit and appear in the Conversations list.
      </p>
    </div>
  );
}
