/**
 * useLocale hook tests. Vitest + jsdom. Renders via the bundled `react-dom`
 * client so we don't pull in `@testing-library/react` (not in deps).
 */
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import i18n, { isRTL, RTL_LOCALES, SUPPORTED_LOCALES } from '../i18n';
import { useLocale } from './useLocale';

// setLocale's PATCH /auth/me call must not hit the network under jsdom.
vi.mock('../lib/api', () => ({
  api: {
    patch: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

function Probe({ onMount }: { onMount: (h: ReturnType<typeof useLocale>) => void }) {
  const h = useLocale();
  onMount(h);
  return null;
}

async function mountProbe(): Promise<ReturnType<typeof useLocale>> {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  let captured: ReturnType<typeof useLocale> | null = null;
  await act(async () => {
    root.render(<Probe onMount={(h) => { captured = h; }} />);
  });
  // captured is populated synchronously during render() inside act().
  return captured as unknown as ReturnType<typeof useLocale>;
}

describe('useLocale', () => {
  beforeEach(async () => {
    window.localStorage.clear();
    await i18n.changeLanguage('en');
  });

  it('returns the active locale and isRTL=false for English', async () => {
    const h = await mountProbe();
    expect(h.locale.slice(0, 2)).toBe('en');
    expect(h.isRTL).toBe(false);
  });

  it('setLocale switches language, persists to localStorage and flips dir', async () => {
    const h = await mountProbe();
    await act(async () => {
      await h.setLocale('ar');
    });
    expect(localStorage.getItem('ec.locale')).toBe('ar');
    expect(document.documentElement.lang).toBe('ar');
    expect(document.documentElement.dir).toBe('rtl');
  });

  it('isRTL helper recognises ar/he/ur and only those', () => {
    expect(isRTL('ar')).toBe(true);
    expect(isRTL('he')).toBe(true);
    expect(isRTL('ur')).toBe(true);
    expect(isRTL('en')).toBe(false);
    expect(isRTL('ja')).toBe(false);
    expect(isRTL('zh')).toBe(false);
    expect(isRTL(undefined)).toBe(false);
    expect(isRTL(null)).toBe(false);
  });

  it('handles region subtags (zh-CN, fr-FR, ar-EG)', () => {
    expect(isRTL('ar-EG')).toBe(true);
    expect(isRTL('zh-CN')).toBe(false);
  });

  it('exposes all 11 locales and tags the right ones as RTL', () => {
    expect(SUPPORTED_LOCALES).toHaveLength(11);
    const rtlCodes = SUPPORTED_LOCALES.filter((l) => l.rtl).map((l) => l.code).sort();
    expect(rtlCodes).toEqual(['ar', 'he', 'ur']);
    expect([...RTL_LOCALES].sort()).toEqual(['ar', 'he', 'ur']);
  });
});
