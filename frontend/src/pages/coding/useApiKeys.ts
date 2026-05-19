import { useCallback, useEffect, useRef, useState } from 'react';
import type { AiProvider } from './types';

/**
 * BYO-API-key vault. Uses Electron `safeStorage` when running inside the
 * desktop shell; falls back to localStorage for web/dev. Always returns the
 * decrypted plaintext via Promise.
 */
const STORAGE_PREFIX = 'ec_apikey_';

function lsKey(provider: AiProvider) {
  return `${STORAGE_PREFIX}${provider}`;
}

const inElectron = () => typeof window !== 'undefined' && !!window.enterpriseCore?.vault;

export async function loadApiKey(provider: AiProvider): Promise<string | null> {
  if (inElectron()) {
    return (await window.enterpriseCore!.vault.get(lsKey(provider))) ?? null;
  }
  return localStorage.getItem(lsKey(provider));
}

export async function saveApiKey(provider: AiProvider, key: string | null): Promise<void> {
  const stored = key && key.trim().length > 0 ? key.trim() : null;
  if (inElectron()) {
    await window.enterpriseCore!.vault.set(lsKey(provider), stored);
    return;
  }
  if (stored === null) {
    localStorage.removeItem(lsKey(provider));
  } else {
    localStorage.setItem(lsKey(provider), stored);
  }
}

export type VaultStatus = { encrypted: boolean; isDesktop: boolean };

export function useApiKeys() {
  const [keys, setKeys] = useState<Record<AiProvider, string | null>>({
    anthropic: null,
    openai: null,
    ollama: null,
  });
  const [status, setStatus] = useState<VaultStatus>({ encrypted: false, isDesktop: false });
  const loaded = useRef(false);

  const refresh = useCallback(async () => {
    const [a, o, l] = await Promise.all([
      loadApiKey('anthropic'),
      loadApiKey('openai'),
      loadApiKey('ollama'),
    ]);
    setKeys({ anthropic: a, openai: o, ollama: l });
    if (inElectron()) {
      const s = await window.enterpriseCore!.vault.available();
      setStatus({ encrypted: !!s.encrypted, isDesktop: true });
    } else {
      setStatus({ encrypted: false, isDesktop: false });
    }
  }, []);

  useEffect(() => {
    if (loaded.current) return;
    loaded.current = true;
    refresh();
  }, [refresh]);

  const update = useCallback(async (provider: AiProvider, value: string | null) => {
    await saveApiKey(provider, value);
    setKeys((prev) => ({ ...prev, [provider]: value && value.trim() ? value.trim() : null }));
  }, []);

  const clearAll = useCallback(async () => {
    await Promise.all([
      saveApiKey('anthropic', null),
      saveApiKey('openai', null),
      saveApiKey('ollama', null),
    ]);
    setKeys({ anthropic: null, openai: null, ollama: null });
  }, []);

  return { keys, status, refresh, update, clearAll };
}
