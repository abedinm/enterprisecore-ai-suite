import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import {
  Bot, Code2, Edit3, Globe, KeyRound, Lock, MessageSquare,
  Plus, PlayCircle, Trash2,
} from 'lucide-react';
import { webchatApi, languageLabel, type BotOut } from '../../lib/webchat';
import { formatDate } from '../../lib/utils';

export function BotList() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const bots = useQuery({
    queryKey: ['webchat', 'bots'],
    queryFn: () => webchatApi.listBots(),
  });

  const remove = useMutation({
    mutationFn: (id: string) => webchatApi.deleteBot(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['webchat', 'bots'] }),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-brand-600">Module workspace</p>
          <h1 className="mt-1 flex items-center gap-2 text-3xl font-semibold">
            <MessageSquare className="text-brand-600" size={26} />
            Web Chat Bots
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-muted">
            Build multilingual chatbots, embed them on any site, and read every
            visitor conversation from this dashboard.
          </p>
        </div>
        <button className="ec-btn-primary" onClick={() => navigate('/webchat/bots/new')}>
          <Plus size={16} /> New bot
        </button>
      </div>

      {bots.isLoading && (
        <p className="text-sm text-ink-muted">Loading bots…</p>
      )}

      {bots.isError && (
        <div className="ec-card border-rose-300 bg-rose-50 p-4 text-sm text-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
          Could not load bots. Make sure your license includes the Web Chat module.
        </div>
      )}

      {bots.data && bots.data.length === 0 && (
        <div className="grid place-items-center rounded-xl border border-dashed border-border bg-surface-muted/40 p-10 text-center">
          <Bot size={28} className="mb-3 text-ink-subtle" />
          <p className="font-semibold">No bots yet</p>
          <p className="mt-1 text-sm text-ink-muted">
            Create your first bot to start collecting conversations.
          </p>
          <button className="ec-btn-primary mt-4" onClick={() => navigate('/webchat/bots/new')}>
            <Plus size={16} /> New bot
          </button>
        </div>
      )}

      {bots.data && bots.data.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {bots.data.map((bot) => (
            <BotCard
              key={bot.id}
              bot={bot}
              onDelete={() => {
                if (confirm(`Delete bot "${bot.name}"? Conversations will be removed too.`)) {
                  remove.mutate(bot.id);
                }
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function BotCard({ bot, onDelete }: { bot: BotOut; onDelete: () => void }) {
  return (
    <div className="ec-card flex h-full flex-col p-5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-base font-semibold">{bot.name}</p>
          {bot.description && (
            <p className="mt-1 line-clamp-2 text-xs text-ink-muted">{bot.description}</p>
          )}
        </div>
        <span
          className={
            bot.is_public
              ? 'ec-badge-green inline-flex items-center gap-1'
              : 'ec-badge bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200 inline-flex items-center gap-1'
          }
          title={bot.is_public ? 'Reachable from the embed widget' : 'Disabled for visitors'}
        >
          {bot.is_public ? <Globe size={11} /> : <Lock size={11} />}
          {bot.is_public ? 'Public' : 'Private'}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-ink-muted">
        <div>
          <p className="uppercase tracking-wider text-ink-subtle">Provider</p>
          <p className="text-ink">{bot.provider}</p>
        </div>
        <div>
          <p className="uppercase tracking-wider text-ink-subtle">Model</p>
          <p className="truncate text-ink" title={bot.model}>{bot.model}</p>
        </div>
        <div>
          <p className="uppercase tracking-wider text-ink-subtle">Language</p>
          <p className="text-ink">{languageLabel(bot.language_preset)}</p>
        </div>
        <div>
          <p className="uppercase tracking-wider text-ink-subtle">Messages</p>
          <p className="text-ink">{bot.system_messages_count}</p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-ink-muted">
        <span className="inline-flex items-center gap-1">
          <KeyRound size={11} /> {bot.has_byo_key ? 'BYO key set' : 'Suite key'}
        </span>
        <span>·</span>
        <span>{bot.rate_limit_per_min}/min</span>
        <span>·</span>
        <span>Created {formatDate(bot.created_at)}</span>
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5">
        <Link to={`/webchat/bots/${bot.id}/conversations`} className="ec-btn-secondary !py-1.5 !px-2.5 text-xs">
          <MessageSquare size={13} /> Conversations
        </Link>
        <Link to={`/webchat/bots/${bot.id}/embed`} className="ec-btn-secondary !py-1.5 !px-2.5 text-xs">
          <Code2 size={13} /> Embed
        </Link>
        <Link to={`/webchat/bots/${bot.id}/sandbox`} className="ec-btn-secondary !py-1.5 !px-2.5 text-xs">
          <PlayCircle size={13} /> Sandbox
        </Link>
        <Link to={`/webchat/bots/${bot.id}/edit`} className="ec-btn-ghost !py-1.5 !px-2.5 text-xs" title="Edit">
          <Edit3 size={13} />
        </Link>
        <button
          type="button"
          className="ec-btn-ghost !py-1.5 !px-2.5 text-xs text-rose-600"
          title="Delete"
          onClick={onDelete}
        >
          <Trash2 size={13} />
        </button>
      </div>
    </div>
  );
}
