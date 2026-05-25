import { describe, expect, it } from 'vitest';
import { DEFAULT_MODEL, PROVIDER_LABELS, PROVIDER_MODELS } from '../providers';

describe('providers catalog', () => {
  it('exposes the three supported providers with labels', () => {
    expect(Object.keys(PROVIDER_LABELS).sort()).toEqual(['anthropic', 'ollama', 'openai']);
  });

  it('every provider has at least one selectable model and the default is in the list', () => {
    for (const p of ['anthropic', 'openai', 'ollama'] as const) {
      expect(PROVIDER_MODELS[p].length).toBeGreaterThan(0);
      expect(PROVIDER_MODELS[p]).toContain(DEFAULT_MODEL[p]);
    }
  });

  it('Anthropic catalog includes the modern Claude Sonnet generation', () => {
    expect(PROVIDER_MODELS.anthropic).toContain('claude-sonnet-4-6');
  });
});
