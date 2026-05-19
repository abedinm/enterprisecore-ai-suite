import type { AiProvider } from './types';

export const PROVIDER_LABELS: Record<AiProvider, string> = {
  anthropic: 'Claude',
  openai: 'OpenAI',
  ollama: 'Ollama (local)',
};

export const PROVIDER_MODELS: Record<AiProvider, string[]> = {
  anthropic: [
    'claude-opus-4-7',
    'claude-sonnet-4-6',
    'claude-haiku-4-5-20251001',
  ],
  openai: [
    'gpt-4o-mini',
    'gpt-4o',
    'gpt-4-turbo',
  ],
  ollama: [
    'llama3.1',
    'llama3.1:70b',
    'qwen2.5-coder',
    'codellama',
    'deepseek-coder',
  ],
};

export const DEFAULT_MODEL: Record<AiProvider, string> = {
  anthropic: 'claude-sonnet-4-6',
  openai: 'gpt-4o-mini',
  ollama: 'llama3.1',
};
