import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Save } from 'lucide-react';
import {
  FONT_OPTIONS,
  marketingApi,
  type ButtonStyle,
  type Density,
  type MarketingSettings,
  type ThemeMode,
} from '../../lib/marketing';

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
          disabled={save.isPending || !form.name.trim()}
        >
          <Save size={16} /> {save.isPending ? 'Saving…' : 'Save settings'}
        </button>
      </div>
    </form>
  );
}
