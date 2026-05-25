import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, KeyRound, MessageSquare, Save, X } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  LANGUAGE_PRESETS, PROVIDERS, webchatApi,
  type BotCreateIn, type ChatProvider, type LanguagePreset,
} from '../../lib/webchat';

export function BotEditor() {
  const { botId } = useParams<{ botId?: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const isEdit = Boolean(botId);

  const existing = useQuery({
    queryKey: ['webchat', 'bot', botId],
    queryFn: () => webchatApi.getBot(botId!),
    enabled: isEdit,
  });

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [languagePreset, setLanguagePreset] = useState<LanguagePreset>('auto');
  const [systemPrompt, setSystemPrompt] = useState('You are a helpful assistant for our visitors.');
  const [provider, setProvider] = useState<ChatProvider>('anthropic');
  const [model, setModel] = useState('claude-3-5-sonnet-latest');
  const [isPublic, setIsPublic] = useState(true);
  const [rateLimit, setRateLimit] = useState(30);
  const [apiKey, setApiKey] = useState('');
  const [showApiKeyField, setShowApiKeyField] = useState(false);

  useEffect(() => {
    if (existing.data) {
      const b = existing.data;
      setName(b.name);
      setDescription(b.description ?? '');
      setLanguagePreset(b.language_preset);
      setSystemPrompt(b.system_prompt);
      setProvider(b.provider);
      setModel(b.model);
      setIsPublic(b.is_public);
      setRateLimit(b.rate_limit_per_min);
    }
  }, [existing.data]);

  const save = useMutation({
    mutationFn: async () => {
      const body: BotCreateIn = {
        name: name.trim(),
        description: description.trim() || null,
        language_preset: languagePreset,
        system_prompt: systemPrompt,
        model: model.trim(),
        provider,
        is_public: isPublic,
        rate_limit_per_min: rateLimit,
      };
      if (apiKey.trim()) body.api_key = apiKey.trim();

      if (isEdit && botId) {
        return webchatApi.updateBot(botId, body);
      }
      return webchatApi.createBot(body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['webchat', 'bots'] });
      if (isEdit) qc.invalidateQueries({ queryKey: ['webchat', 'bot', botId] });
      toast.success(isEdit ? 'Bot updated' : 'Bot created');
      navigate('/webchat');
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } }; message?: string })
        .response?.data?.detail ?? (err as Error).message ?? 'Failed to save bot';
      toast.error(typeof detail === 'string' ? detail : 'Failed to save bot');
    },
  });

  const clearKey = useMutation({
    mutationFn: () => webchatApi.updateBot(botId!, { clear_api_key: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['webchat', 'bot', botId] });
      qc.invalidateQueries({ queryKey: ['webchat', 'bots'] });
      toast.success('API key cleared');
      setApiKey('');
      setShowApiKeyField(false);
    },
  });

  const hasByoKey = existing.data?.has_byo_key ?? false;

  function handleProviderChange(next: ChatProvider) {
    setProvider(next);
    const defaults = PROVIDERS.find((p) => p.value === next);
    if (defaults && (!model || PROVIDERS.some((p) => p.defaultModel === model))) {
      setModel(defaults.defaultModel);
    }
  }

  if (isEdit && existing.isLoading) {
    return <p className="text-sm text-ink-muted">Loading bot…</p>;
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <button
            type="button"
            className="ec-btn-ghost mb-2 !px-2 !py-1 text-xs"
            onClick={() => navigate('/webchat')}
          >
            <ArrowLeft size={14} /> Back to bots
          </button>
          <h1 className="flex items-center gap-2 text-2xl font-semibold sm:text-3xl">
            <MessageSquare className="text-brand-600" size={24} />
            {isEdit ? 'Edit bot' : 'New bot'}
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-muted">
            Configure the bot persona, provider, and rate limits. Use a BYO key
            to bill against your own API account, or leave it blank to use the
            suite's shared credentials.
          </p>
        </div>
      </div>

      <form
        className="ec-card space-y-5 p-5"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="ec-label">Name</label>
            <input
              className="ec-input"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Support Concierge"
            />
          </div>
          <div>
            <label className="ec-label">Language preset</label>
            <select
              className="ec-input"
              value={languagePreset}
              onChange={(e) => setLanguagePreset(e.target.value as LanguagePreset)}
            >
              {LANGUAGE_PRESETS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="ec-label">Description</label>
            <input
              className="ec-input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Short note about what this bot does (optional)"
            />
          </div>
          <div className="md:col-span-2">
            <label className="ec-label">System prompt</label>
            <textarea
              className="ec-input min-h-[140px]"
              required
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="Describe the persona, tone, and topics this bot should cover."
            />
          </div>
        </div>

        <div className="border-t border-border pt-5">
          <p className="text-sm font-semibold">Provider</p>
          <p className="mt-1 text-xs text-ink-muted">
            Pick where this bot's completions run. Ollama keeps everything on-device.
          </p>
          <div className="mt-3 grid gap-2 md:grid-cols-3">
            {PROVIDERS.map((opt) => (
              <label
                key={opt.value}
                className={
                  'flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 text-sm transition ' +
                  (provider === opt.value
                    ? 'border-brand-500 bg-brand-600/10'
                    : 'border-border hover:bg-surface-muted')
                }
              >
                <input
                  type="radio"
                  className="mt-1"
                  name="provider"
                  value={opt.value}
                  checked={provider === opt.value}
                  onChange={() => handleProviderChange(opt.value)}
                />
                <span>
                  <span className="block font-medium text-ink">{opt.label}</span>
                  <span className="block text-xs text-ink-muted">default {opt.defaultModel}</span>
                </span>
              </label>
            ))}
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div>
              <label className="ec-label">Model</label>
              <input
                className="ec-input font-mono"
                required
                value={model}
                onChange={(e) => setModel(e.target.value)}
              />
            </div>
            <div>
              <label className="ec-label">Rate limit (per minute)</label>
              <input
                type="number"
                className="ec-input"
                min={1}
                max={600}
                value={rateLimit}
                onChange={(e) => setRateLimit(Math.max(1, Number(e.target.value) || 1))}
              />
            </div>
          </div>
        </div>

        <div className="border-t border-border pt-5">
          <p className="text-sm font-semibold flex items-center gap-2">
            <KeyRound size={14} /> BYO API key
          </p>
          <p className="mt-1 text-xs text-ink-muted">
            Stored encrypted on this server. Leave the suite key in place if you
            don't have a dedicated key for this provider.
          </p>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            {isEdit && hasByoKey && !showApiKeyField && (
              <>
                <span className="ec-badge-green inline-flex items-center gap-1">
                  <KeyRound size={11} /> BYO key configured
                </span>
                <button type="button" className="ec-btn-secondary" onClick={() => setShowApiKeyField(true)}>
                  Replace key
                </button>
                <button
                  type="button"
                  className="ec-btn-ghost text-rose-600"
                  disabled={clearKey.isPending}
                  onClick={() => {
                    if (confirm('Clear the BYO API key for this bot?')) clearKey.mutate();
                  }}
                >
                  Clear key
                </button>
              </>
            )}
            {((isEdit && (!hasByoKey || showApiKeyField)) || !isEdit) && (
              <div className="flex-1 min-w-[260px]">
                <label className="ec-label">{hasByoKey ? 'Replacement API key' : 'API key (optional)'}</label>
                <input
                  type="password"
                  className="ec-input"
                  autoComplete="off"
                  placeholder="sk-..."
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                />
              </div>
            )}
            {isEdit && hasByoKey && showApiKeyField && (
              <button
                type="button"
                className="ec-btn-ghost"
                onClick={() => { setApiKey(''); setShowApiKeyField(false); }}
              >
                <X size={14} /> Cancel
              </button>
            )}
            {!isEdit && !hasByoKey && (
              <button
                type="button"
                className="ec-btn-secondary"
                onClick={() => setShowApiKeyField((v) => !v)}
              >
                {showApiKeyField ? 'Hide' : 'Set BYO key'}
              </button>
            )}
          </div>
        </div>

        <div className="border-t border-border pt-5">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            <span>
              <span className="block font-medium">Public</span>
              <span className="block text-xs text-ink-muted">
                When off, the embed widget will refuse all incoming messages.
              </span>
            </span>
          </label>
        </div>

        <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-4">
          <button
            type="button"
            className="ec-btn-secondary"
            onClick={() => navigate('/webchat')}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="ec-btn-primary"
            disabled={save.isPending || !name.trim() || !systemPrompt.trim() || !model.trim()}
          >
            <Save size={16} /> {save.isPending ? 'Saving…' : isEdit ? 'Save changes' : 'Create bot'}
          </button>
        </div>
      </form>
    </div>
  );
}
