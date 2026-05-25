/**
 * Locale read/write hook. Reads from i18next, persists to localStorage and
 * (best-effort) pushes the new preference to the user's profile on the
 * backend so subsequent sessions remember it.
 *
 * Returns:
 *   - `locale`   — the active 2-letter locale code (`en`, `ar`, `zh`, …)
 *   - `setLocale(code)` — switch language; persists + updates `<html lang/dir>`
 *   - `isRTL`    — convenience flag for the active locale
 */
import { useCallback, useEffect, useState } from 'react';
import i18n, { applyDocumentLocale, isRTL as _isRTL, SupportedLocale } from '../i18n';
import { api } from '../lib/api';

export function useLocale() {
  const [locale, setLocaleState] = useState<string>(i18n.language || 'en');

  // Keep React state in sync if some other code triggers a languageChanged.
  useEffect(() => {
    const handler = (lng: string) => setLocaleState(lng);
    i18n.on('languageChanged', handler);
    return () => {
      i18n.off('languageChanged', handler);
    };
  }, []);

  const setLocale = useCallback(async (code: SupportedLocale | string) => {
    await i18n.changeLanguage(code);
    try {
      localStorage.setItem('ec.locale', code);
    } catch {
      /* localStorage may be blocked — ignore. */
    }
    applyDocumentLocale(code);
    // Push to backend; failure is non-fatal (e.g. logged-out, offline).
    try {
      await api.patch('/auth/me', { locale: code });
    } catch {
      /* ignore — local pref still applied */
    }
  }, []);

  return { locale, setLocale, isRTL: _isRTL(locale) };
}
