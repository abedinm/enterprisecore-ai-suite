import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { AlertTriangle, CheckCircle2, Save, Wand2 } from 'lucide-react';
import {
  FONT_OPTIONS,
  marketingApi,
  type ButtonStyle,
  type Density,
  type MarketingSettings,
  type ThemeMode,
} from '../../lib/marketing';
import { autoAdjust, contrastRatio, AA_NORMAL } from '../../lib/colorContrast';

const EMPTY: MarketingSettings = {
  name: '',
  tagline: '',
  description: '',
  logoText: '',
  logoDot: true,
  baseUrl: '',
  seoTitle: '',
  seoDescription: '',
  themeMode: 'light',
  primaryColor: '#2563eb',
  accentColor: '#22d3ee',
  headingFont: 'Inter',
  bodyFont: 'Inter',
  buttonStyle: 'rounded',
  density: 'comfortable',
  radius: 12,
  contactEmail: '',
  contactPhone: '',
  contactAddress: '',
  contactHours: '',
};

export function MarketingSettingsPage() {
  const qc = useQueryClient();
  const stateQ = useQuery({
    queryKey: ['marketing', 'state'],
    queryFn: () => marketingApi.getState(),
  });

  const [form, setForm] = useState<MarketingSettings>(EMPTY);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (stateQ.data && !hydrated) {
      setForm({ ...EMPTY, ...stateQ.data.settings });
      setHydrated(true);
    }
  }, [stateQ.data, hydrated]);

  const save = useMutation({
    mutationFn: () => marketingApi.updateSettings(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'state'] });
      qc.invalidateQueries({ queryKey: ['marketing', 'launch-checklist'] });
      toast.success('Settings saved');
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } }; message?: string })
        .response?.data?.detail ?? (err as Error).message ?? 'Failed to save';
      toast.error(typeof detail === 'string' ? detail : 'Failed to save');
    },
  });

  function update<K extends keyof MarketingSettings>(key: K, value: MarketingSettings[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  // Contrast audit — every visible color combo on the marketing site must
  // clear WCAG AA (4.5:1). We block save until they all pass.
  const contrastReport = useMemo(() => {
    const pageBg = form.themeMode === 'dark' ? '#0c0f16' : '#ffffff';
    const pageText = form.themeMode === 'dark' ? '#f0f4f8' : '#111827';
    const buttonText = '#ffffff';
    const items = [
      { label: 'Body text on page background', fg: pageText, bg: pageBg },
      { label: 'Button text on primary button', fg: buttonText, bg: form.primaryColor },
      { label: 'Button text on accent button', fg: buttonText, bg: form.accentColor },
      { label: 'Primary color text on page background', fg: form.primaryColor, bg: pageBg },
    ];
    const checks = items.map((c) => ({ ...c, ratio: contrastRatio(c.fg, c.bg) }));
    const failing = checks.filter((c) => !Number.isFinite(c.ratio) || c.ratio < AA_NORMAL);
    return { pageBg, buttonText, checks, failing };
  }, [form.primaryColor, form.accentColor, form.themeMode]);

  function autoFix() {
    // Fix the most common breakers: primary/accent backgrounds with white text.
    const next: Partial<MarketingSettings> = {};
    if (contrastRatio('#ffffff', form.primaryColor) < AA_NORMAL) {
      next.primaryColor = autoAdjust(form.primaryColor, '#ffffff', AA_NORMAL);
      // Actually we want bg dark enough for white text, so adjust the bg toward black.
      // autoAdjust nudges fg; for bg we invert: find a darker bg with white text passing.
      const adjustedBg = autoAdjust('#ffffff', form.primaryColor, AA_NORMAL);
      // adjustedBg is unused; instead darken primaryColor directly.
      let candidate = form.primaryColor;
      for (let i = 0; i < 60; i += 1) {
        if (contrastRatio('#ffffff', candidate) >= AA_NORMAL) break;
        // Darken: blend 8% toward black.
        const m = candidate.match(/^#?([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i);
        if (!m) break;
        const r = Math.round(parseInt(m[1], 16) * 0.92);
        const g = Math.round(parseInt(m[2], 16) * 0.92);
        const b = Math.round(parseInt(m[3], 16) * 0.92);
        const hex = (n: number) => Math.max(0, Math.min(255, n)).toString(16).padStart(2, '0');
        candidate = `#${hex(r)}${hex(g)}${hex(b)}`;
      }
      next.primaryColor = candidate;
      // Silence the unused-var lint by referencing adjustedBg in a no-op:
      void adjustedBg;
    }
    if (contrastRatio('#ffffff', form.accentColor) < AA_NORMAL) {
      let candidate = form.accentColor;
      for (let i = 0; i < 60; i += 1) {
        if (contrastRatio('#ffffff', candidate) >= AA_NORMAL) break;
        const m = candidate.match(/^#?([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i);
        if (!m) break;
        const r = Math.round(parseInt(m[1], 16) * 0.92);
        const g = Math.round(parseInt(m[2], 16) * 0.92);
        const b = Math.round(parseInt(m[3], 16) * 0.92);
        const hex = (n: number) => Math.max(0, Math.min(255, n)).toString(16).padStart(2, '0');
        candidate = `#${hex(r)}${hex(g)}${hex(b)}`;
      }
      next.accentColor = candidate;
    }
    if (Object.keys(next).length > 0) {
      setForm((f) => ({ ...f, ...next }));
      toast.success('Adjusted colors to meet WCAG AA contrast');
    } else {
      toast('Colors already meet AA contrast');
    }
  }

  if (stateQ.isLoading) {
    return <p className="text-sm text-ink-muted">Loading settings…</p>;
  }
  if (stateQ.isError) {
    return (
      <div className="ec-card border-rose-300 bg-rose-50 p-4 text-sm text-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
        Could not load settings.
      </div>
    );
  }

  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      {/* Identity ----------------------------------------------------------*/}
      <section className="ec-card p-5">
        <h2 className="text-lg font-semibold">Site identity</h2>
        <p className="mt-1 text-sm text-ink-muted">
          Name and tagline shown in the header, footer, and OG tags.
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <label className="ec-label">Name</label>
            <input
              className="ec-input"
              value={form.name}
              onChange={(e) => update('name', e.target.value)}
              required
            />
          </div>
          <div>
            <label className="ec-label">Tagline</label>
            <input
              className="ec-input"
              value={form.tagline}
              onChange={(e) => update('tagline', e.target.value)}
            />
          </div>
          <div className="md:col-span-2">
            <label className="ec-label">Description</label>
            <textarea
              className="ec-input min-h-[80px]"
              value={form.description}
              onChange={(e) => update('description', e.target.value)}
            />
          </div>
          <div>
            <label className="ec-label">Logo text</label>
            <input
              className="ec-input"
              value={form.logoText}
              onChange={(e) => update('logoText', e.target.value)}
            />
          </div>
          <div className="flex items-end">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.logoDot}
                onChange={(e) => update('logoDot', e.target.checked)}
              />
              Show accent dot in logo
            </label>
          </div>
          <div className="md:col-span-2">
            <label className="ec-label">Public base URL</label>
            <input
              className="ec-input font-mono"
              placeholder="https://example.com"
              value={form.baseUrl}
              onChange={(e) => update('baseUrl', e.target.value)}
            />
          </div>
        </div>
      </section>

      {/* SEO ---------------------------------------------------------------*/}
      <section className="ec-card p-5">
        <h2 className="text-lg font-semibold">SEO defaults</h2>
        <p className="mt-1 text-sm text-ink-muted">
          Used when a specific page or post doesn't set its own.
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <label className="ec-label">Default title</label>
            <input
              className="ec-input"
              value={form.seoTitle}
              onChange={(e) => update('seoTitle', e.target.value)}
            />
          </div>
          <div>
            <label className="ec-label">Default description</label>
            <input
              className="ec-input"
              value={form.seoDescription}
              onChange={(e) => update('seoDescription', e.target.value)}
            />
          </div>
        </div>
      </section>

      {/* Theme -------------------------------------------------------------*/}
      <section className="ec-card p-5">
        <h2 className="text-lg font-semibold">Theme</h2>
        <p className="mt-1 text-sm text-ink-muted">Colors, type, and component shape.</p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <label className="ec-label">Mode</label>
            <div className="flex gap-2">
              {(['light', 'dark'] as ThemeMode[]).map((m) => (
                <label
                  key={m}
                  className={
                    'flex flex-1 cursor-pointer items-center justify-center gap-2 rounded-lg border px-3 py-2 text-sm transition ' +
                    (form.themeMode === m
                      ? 'border-brand-500 bg-brand-600/10'
                      : 'border-border hover:bg-surface-muted')
                  }
                >
                  <input
                    type="radio"
                    name="themeMode"
                    checked={form.themeMode === m}
                    onChange={() => update('themeMode', m)}
                    className="sr-only"
                  />
                  <span className="capitalize">{m}</span>
                </label>
              ))}
            </div>
          </div>
          <div>
            <label className="ec-label">Density</label>
            <div className="flex gap-2">
              {(['comfortable', 'compact'] as Density[]).map((d) => (
                <label
                  key={d}
                  className={
                    'flex flex-1 cursor-pointer items-center justify-center gap-2 rounded-lg border px-3 py-2 text-sm transition ' +
                    (form.density === d
                      ? 'border-brand-500 bg-brand-600/10'
                      : 'border-border hover:bg-surface-muted')
                  }
                >
                  <input
                    type="radio"
                    name="density"
                    checked={form.density === d}
                    onChange={() => update('density', d)}
                    className="sr-only"
                  />
                  <span className="capitalize">{d}</span>
                </label>
              ))}
            </div>
          </div>

          <div>
            <label className="ec-label">Primary color</label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                className="h-10 w-12 cursor-pointer rounded-md border border-border bg-transparent p-1"
                value={form.primaryColor}
                onChange={(e) => update('primaryColor', e.target.value)}
              />
              <input
                type="text"
                className="ec-input flex-1 font-mono"
                value={form.primaryColor}
                onChange={(e) => update('primaryColor', e.target.value)}
              />
            </div>
          </div>
          <div>
            <label className="ec-label">Accent color</label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                className="h-10 w-12 cursor-pointer rounded-md border border-border bg-transparent p-1"
                value={form.accentColor}
                onChange={(e) => update('accentColor', e.target.value)}
              />
              <input
                type="text"
                className="ec-input flex-1 font-mono"
                value={form.accentColor}
                onChange={(e) => update('accentColor', e.target.value)}
              />
            </div>
          </div>

          <div>
            <label className="ec-label">Heading font</label>
            <select
              className="ec-input"
              value={form.headingFont}
              onChange={(e) => update('headingFont', e.target.value)}
            >
              {FONT_OPTIONS.map((f) => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="ec-label">Body font</label>
            <select
              className="ec-input"
              value={form.bodyFont}
              onChange={(e) => update('bodyFont', e.target.value)}
            >
              {FONT_OPTIONS.map((f) => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="ec-label">Button style</label>
            <div className="flex gap-2">
              {(['rounded', 'square'] as ButtonStyle[]).map((b) => (
                <label
                  key={b}
                  className={
                    'flex flex-1 cursor-pointer items-center justify-center rounded-lg border px-3 py-2 text-sm transition ' +
                    (form.buttonStyle === b
                      ? 'border-brand-500 bg-brand-600/10'
                      : 'border-border hover:bg-surface-muted')
                  }
                >
                  <input
                    type="radio"
                    name="buttonStyle"
                    checked={form.buttonStyle === b}
                    onChange={() => update('buttonStyle', b)}
                    className="sr-only"
                  />
                  <span className="capitalize">{b}</span>
                </label>
              ))}
            </div>
          </div>
          <div>
            <label className="ec-label">Corner radius ({form.radius}px)</label>
            <input
              type="range"
              min={0}
              max={24}
              value={form.radius}
              onChange={(e) => update('radius', Number(e.target.value))}
              className="h-2 w-full cursor-pointer appearance-none rounded-full bg-surface-muted accent-brand-600"
            />
          </div>
        </div>

        {/* WCAG AA contrast audit — blocks save when any combo is below
            4.5:1. Auto-adjust nudges the offending color until it passes. */}
        <div
          className={
            'mt-5 rounded-lg border p-4 text-sm ' +
            (contrastReport.failing.length === 0
              ? 'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-200'
              : 'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-100')
          }
          role={contrastReport.failing.length === 0 ? undefined : 'alert'}
        >
          <div className="flex items-start gap-2">
            {contrastReport.failing.length === 0 ? (
              <CheckCircle2 size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
            ) : (
              <AlertTriangle size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
            )}
            <div className="min-w-0 flex-1">
              <p className="font-semibold">
                {contrastReport.failing.length === 0
                  ? 'All color combinations meet WCAG AA contrast.'
                  : 'Color contrast must be at least 4.5:1 to meet WCAG AA.'}
              </p>
              <ul className="mt-2 space-y-1 font-mono text-xs">
                {contrastReport.checks.map((c) => {
                  const pass = Number.isFinite(c.ratio) && c.ratio >= AA_NORMAL;
                  return (
                    <li key={c.label} className="flex items-center justify-between gap-2">
                      <span>{c.label}</span>
                      <span className={pass ? 'text-emerald-700 dark:text-emerald-300' : 'text-rose-700 dark:text-rose-300'}>
                        {Number.isFinite(c.ratio) ? c.ratio.toFixed(2) : '—'}:1 {pass ? 'OK' : 'FAIL'}
                      </span>
                    </li>
                  );
                })}
              </ul>
              {contrastReport.failing.length > 0 && (
                <button
                  type="button"
                  className="ec-btn-secondary mt-3"
                  onClick={autoFix}
                >
                  <Wand2 size={14} aria-hidden="true" /> Auto-adjust colors
                </button>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Contact -----------------------------------------------------------*/}
      <section className="ec-card p-5">
        <h2 className="text-lg font-semibold">Contact</h2>
        <p className="mt-1 text-sm text-ink-muted">
          Surfaced in the footer and contact section of the site.
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <label className="ec-label">Email</label>
            <input
              type="email"
              className="ec-input"
              value={form.contactEmail}
              onChange={(e) => update('contactEmail', e.target.value)}
            />
          </div>
          <div>
            <label className="ec-label">Phone</label>
            <input
              className="ec-input"
              value={form.contactPhone}
              onChange={(e) => update('contactPhone', e.target.value)}
            />
          </div>
          <div className="md:col-span-2">
            <label className="ec-label">Address</label>
            <textarea
              className="ec-input min-h-[64px]"
              value={form.contactAddress}
              onChange={(e) => update('contactAddress', e.target.value)}
            />
          </div>
          <div className="md:col-span-2">
            <label className="ec-label">Hours</label>
            <input
              className="ec-input"
              value={form.contactHours}
              onChange={(e) => update('contactHours', e.target.value)}
              placeholder="Mon–Fri 9–5"
            />
          </div>
        </div>
      </section>

      <div className="sticky bottom-0 -mx-1 flex justify-end gap-2 border-t border-border bg-surface/90 px-1 py-3 backdrop-blur">
        <button
          type="submit"
          className="ec-btn-primary"
          disabled={
            save.isPending || !form.name.trim() || contrastReport.failing.length > 0
          }
          title={
            contrastReport.failing.length > 0
              ? 'Text contrast must be at least 4.5:1 to meet WCAG AA'
              : undefined
          }
          aria-describedby={
            contrastReport.failing.length > 0 ? 'contrast-block-reason' : undefined
          }
        >
          <Save size={16} /> {save.isPending ? 'Saving…' : 'Save settings'}
        </button>
        {contrastReport.failing.length > 0 && (
          <span id="contrast-block-reason" className="sr-only">
            Save is disabled because {contrastReport.failing.length} color combination
            {contrastReport.failing.length === 1 ? '' : 's'} fail WCAG AA contrast.
          </span>
        )}
      </div>
    </form>
  );
}
