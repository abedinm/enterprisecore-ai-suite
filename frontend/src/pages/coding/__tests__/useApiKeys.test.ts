import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadApiKey, saveApiKey } from '../useApiKeys';

describe('useApiKeys vault (web fallback)', () => {
  afterEach(() => {
    window.localStorage.clear();
  });

  it('round-trips a Claude key through localStorage when no Electron bridge', async () => {
    await saveApiKey('anthropic', 'sk-ant-test-1234');
    expect(window.localStorage.getItem('ec_apikey_anthropic')).toBe('sk-ant-test-1234');
    await expect(loadApiKey('anthropic')).resolves.toBe('sk-ant-test-1234');
  });

  it('clears a key when null/empty is passed', async () => {
    await saveApiKey('openai', 'sk-temp');
    await saveApiKey('openai', null);
    expect(window.localStorage.getItem('ec_apikey_openai')).toBeNull();
    await expect(loadApiKey('openai')).resolves.toBeNull();

    await saveApiKey('openai', '   ');  // whitespace-only counts as empty
    expect(window.localStorage.getItem('ec_apikey_openai')).toBeNull();
  });

  it('trims surrounding whitespace before persisting', async () => {
    await saveApiKey('anthropic', '  sk-ant-padded  ');
    await expect(loadApiKey('anthropic')).resolves.toBe('sk-ant-padded');
  });

  it('routes through the Electron vault when window.enterpriseCore is present', async () => {
    const setSpy = vi.fn().mockResolvedValue(true);
    const getSpy = vi.fn().mockResolvedValue('sk-vault-value');
    (window as any).enterpriseCore = {
      isDesktop: true, platform: 'win32',
      getBackendUrl: vi.fn(), getPlatform: vi.fn(),
      vault: {
        get: getSpy, set: setSpy,
        listKeys: vi.fn(), clear: vi.fn(),
        available: vi.fn().mockResolvedValue({ encrypted: true }),
      },
      dialog: { openDirectory: vi.fn(), openFile: vi.fn(), saveFile: vi.fn() },
      shell: { openExternal: vi.fn() },
      on: vi.fn().mockReturnValue(() => {}),
    };

    await saveApiKey('anthropic', 'sk-ant-vault');
    expect(setSpy).toHaveBeenCalledWith('ec_apikey_anthropic', 'sk-ant-vault');
    // Should NOT touch localStorage when desktop vault is active
    expect(window.localStorage.getItem('ec_apikey_anthropic')).toBeNull();

    await expect(loadApiKey('anthropic')).resolves.toBe('sk-vault-value');
    expect(getSpy).toHaveBeenCalledWith('ec_apikey_anthropic');
  });
});
