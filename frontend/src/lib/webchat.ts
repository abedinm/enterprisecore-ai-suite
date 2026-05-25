import { api, API_BASE } from './api';

export type LanguagePreset = 'auto' | 'en' | 'bn' | 'hi' | 'ur';
export type ChatProvider = 'anthropic' | 'openai' | 'ollama';

export type BotOut = {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  language_preset: LanguagePreset;
  system_prompt: string;
  model: string;
  provider: ChatProvider;
  is_public: boolean;
  has_byo_key: boolean;
  rate_limit_per_min: number;
  system_messages_count: number;
  created_at: string;
  updated_at: string;
  embed_snippet: string;
};

export type BotCreateIn = {
  name: string;
  description?: string | null;
  language_preset: LanguagePreset;
  system_prompt: string;
  model: string;
  provider: ChatProvider;
  is_public: boolean;
  api_key?: string | null;
  rate_limit_per_min: number;
};

export type BotUpdateIn = Partial<BotCreateIn> & {
  clear_api_key?: boolean;
};

export type ConversationOut = {
  id: string;
  bot_id: string;
  visitor_session_id: string;
  contact_hint: string | null;
  language_detected: string | null;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
};

export type ChatMessageOut = {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system' | string;
  content: string;
  language_detected: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  created_at: string;
};

export type ConversationWithMessagesOut = ConversationOut & {
  messages: ChatMessageOut[];
};

export type PublicChatIn = {
  visitor_session_id: string;
  message: string;
  contact_hint?: string | null;
};

export type PublicChatOut = {
  reply: string;
  conversation_id: string;
  message_id: string;
  language_detected: string | null;
};

export const webchatApi = {
  listBots: () => api.get<BotOut[]>('/webchat/bots').then((r) => r.data),
  createBot: (body: BotCreateIn) =>
    api.post<BotOut>('/webchat/bots', body).then((r) => r.data),
  getBot: (id: string) => api.get<BotOut>(`/webchat/bots/${id}`).then((r) => r.data),
  updateBot: (id: string, body: BotUpdateIn) =>
    api.patch<BotOut>(`/webchat/bots/${id}`, body).then((r) => r.data),
  deleteBot: (id: string) =>
    api.delete(`/webchat/bots/${id}`).then(() => true),

  listConversations: (botId: string, limit = 50) =>
    api
      .get<ConversationOut[]>(`/webchat/bots/${botId}/conversations`, { params: { limit } })
      .then((r) => r.data),
  getConversation: (conversationId: string) =>
    api
      .get<ConversationWithMessagesOut>(`/webchat/conversations/${conversationId}`)
      .then((r) => r.data),

  /** Public, no-auth widget endpoint. Posts a visitor message to the bot. */
  publicChat: (botId: string, body: PublicChatIn) =>
    fetch(`${API_BASE}/webchat/chat/${botId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) {
        const detail = await r.text().catch(() => `HTTP ${r.status}`);
        throw new Error(detail);
      }
      return (await r.json()) as PublicChatOut;
    }),
};

export const LANGUAGE_PRESETS: { value: LanguagePreset; label: string }[] = [
  { value: 'auto', label: 'Auto-detect' },
  { value: 'en', label: 'English' },
  { value: 'bn', label: 'Bengali' },
  { value: 'hi', label: 'Hindi' },
  { value: 'ur', label: 'Urdu' },
];

export const PROVIDERS: { value: ChatProvider; label: string; defaultModel: string }[] = [
  { value: 'anthropic', label: 'Anthropic', defaultModel: 'claude-3-5-sonnet-latest' },
  { value: 'openai', label: 'OpenAI', defaultModel: 'gpt-4o-mini' },
  { value: 'ollama', label: 'Ollama (local)', defaultModel: 'llama3.1' },
];

export function languageLabel(value: string | null | undefined): string {
  if (!value) return '—';
  const v = value.toLowerCase();
  const map: Record<string, string> = { auto: 'Auto', en: 'EN', bn: 'BN', hi: 'HI', ur: 'UR' };
  return map[v] ?? value.toUpperCase();
}
