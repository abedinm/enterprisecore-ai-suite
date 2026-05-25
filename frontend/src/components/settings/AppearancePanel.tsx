/**
 * AppearancePanel — one-stop appearance + accessibility settings:
 *
 *   - Theme (light / dark / system) with animated icon switch
 *   - Palette (indigo / aurora / sunset / forest / ocean / mono)
 *   - Density (comfortable / compact)
 *   - Ambient (none / aurora / mesh / grid)
 *   - Motion (auto / on / off)
 *   - Sound (on / off)
 *
 * Each control gives instant feedback (the page itself recolors as the
 * palette is picked, the density flexes, the ambient layer fades).
 */
import { motion } from 'framer-motion';
import {
  Cloud,
  Compass,
  Grid3x3,
  Moon,
  Music,
  PaintBucket,
  Sparkles,
  Sun,
  Sunset,
  TreePine,
  Type,
  Waves,
  Zap,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { setSoundEnabled } from '../../lib/celebrate';
import { useThemeStore, type AmbientFx, type Density, type Palette, type Theme } from '../../store/theme';

const PALETTE_OPTIONS: { value: Palette; label: string; swatch: string; icon: typeof PaintBucket }[] = [
  { value: 'indigo', label: 'Indigo',  swatch: 'linear-gradient(135deg,#818cf8,#4f46e5)',  icon: Sparkles },
  { value: 'aurora', label: 'Aurora',  swatch: 'linear-gradient(135deg,#2dd4bf,#0d9488)',  icon: Cloud },
  { value: 'sunset', label: 'Sunset',  swatch: 'linear-gradient(135deg,#fb923c,#ea580c)',  icon: Sunset },
  { value: 'forest', label: 'Forest',  swatch: 'linear-gradient(135deg,#4ade80,#16a34a)',  icon: TreePine },
  { value: 'ocean',  label: 'Ocean',   swatch: 'linear-gradient(135deg,#22d3ee,#0891b2)',  icon: Waves },
  { value: 'mono',   label: 'Mono',    swatch: 'linear-gradient(135deg,#9ca3af,#4b5563)',  icon: Compass },
];

const AMBIENT_OPTIONS: { value: AmbientFx; label: string; icon: typeof Cloud }[] = [
  { value: 'aurora', label: 'Aurora', icon: Cloud },
  { value: 'mesh',   label: 'Mesh',   icon: Waves },
  { value: 'grid',   label: 'Grid',   icon: Grid3x3 },
  { value: 'none',   label: 'None',   icon: Zap },
];

export function AppearancePanel() {
  const theme = useThemeStore(s => s.theme);
  const palette = useThemeStore(s => s.palette);
  const density = useThemeStore(s => s.density);
  const ambient = useThemeStore(s => s.ambient);
  const motionPref = useThemeStore(s => s.motionPref);
  const setTheme = useThemeStore(s => s.setTheme);
  const setPalette = useThemeStore(s => s.setPalette);
  const setDensity = useThemeStore(s => s.setDensity);
  const setAmbient = useThemeStore(s => s.setAmbient);
  const setMotionPref = useThemeStore(s => s.setMotionPref);

  const [sound, setSound] = useState<boolean>(() => {
    try { return localStorage.getItem('ec.sound') === 'on'; } catch { return false; }
  });
  useEffect(() => { setSoundEnabled(sound); }, [sound]);

  return (
    <div className="space-y-8">
      {/* Theme */}
      <Section
        title="Theme"
        description="Pick light, dark, or follow your system."
        icon={Sun}
      >
        <div className="grid grid-cols-3 gap-3">
          {(['light', 'dark', 'system'] as Theme[]).map((t) => (
            <SegmentCard
              key={t}
              selected={theme === t}
              onClick={() => setTheme(t)}
              label={t === 'system' ? 'System' : t === 'light' ? 'Light' : 'Dark'}
              icon={t === 'light' ? Sun : t === 'dark' ? Moon : Sparkles}
            />
          ))}
        </div>
      </Section>

      {/* Palette */}
      <Section
        title="Colour palette"
        description="The brand colour everything in the app pulls from."
        icon={PaintBucket}
      >
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
          {PALETTE_OPTIONS.map(({ value, label, swatch, icon: Icon }) => {
            const active = palette === value;
            return (
              <motion.button
                key={value}
                type="button"
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => setPalette(value)}
                className={`relative flex items-center gap-3 rounded-xl border px-3 py-2.5 text-sm transition ${
                  active ? 'border-brand-500 ring-2 ring-brand-500/30' : 'border-border hover:border-ink-subtle'
                }`}
              >
                <span
                  className="grid h-9 w-9 place-items-center rounded-lg text-white shadow-sm"
                  style={{ background: swatch }}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                </span>
                <span className="font-medium">{label}</span>
                {active && (
                  <motion.span
                    layoutId="palette-active"
                    className="absolute inset-0 -z-10 rounded-xl bg-brand-500/8"
                    transition={{ type: 'spring', stiffness: 360, damping: 28 }}
                  />
                )}
              </motion.button>
            );
          })}
        </div>
      </Section>

      {/* Ambient background */}
      <Section
        title="Ambient background"
        description="A subtle animated layer behind your content. Off keeps the canvas flat."
        icon={Cloud}
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {AMBIENT_OPTIONS.map(({ value, label, icon: Icon }) => (
            <SegmentCard
              key={value}
              selected={ambient === value}
              onClick={() => setAmbient(value)}
              label={label}
              icon={Icon}
            />
          ))}
        </div>
      </Section>

      {/* Density */}
      <Section
        title="Density"
        description="Comfortable feels roomier; compact fits more on screen."
        icon={Type}
      >
        <div className="grid grid-cols-2 gap-3">
          {(['comfortable', 'compact'] as Density[]).map((d) => (
            <SegmentCard
              key={d}
              selected={density === d}
              onClick={() => setDensity(d)}
              label={d === 'comfortable' ? 'Comfortable' : 'Compact'}
              icon={Type}
            />
          ))}
        </div>
      </Section>

      {/* Motion */}
      <Section
        title="Animations"
        description="Honours your OS reduced-motion preference by default. Override here if you want."
        icon={Zap}
      >
        <div className="grid grid-cols-3 gap-3">
          {(['auto', 'on', 'off'] as const).map((m) => (
            <SegmentCard
              key={m}
              selected={motionPref === m}
              onClick={() => setMotionPref(m)}
              label={m === 'auto' ? 'Auto' : m === 'on' ? 'Always on' : 'Off'}
              icon={Zap}
            />
          ))}
        </div>
      </Section>

      {/* Sound */}
      <Section
        title="Sound"
        description="A soft chime when an achievement unlocks. Off by default."
        icon={Music}
      >
        <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-surface-elevated p-3">
          <span id="sound-toggle-label" className="text-sm">Achievement chime</span>
          <button
            type="button"
            role="switch"
            aria-checked={sound}
            aria-labelledby="sound-toggle-label"
            onClick={() => setSound((s) => !s)}
            className={`relative inline-flex h-6 w-11 cursor-pointer items-center rounded-full transition focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 ${
              sound ? 'bg-brand-600' : 'bg-surface-muted'
            }`}
          >
            <motion.span
              aria-hidden="true"
              className="absolute h-5 w-5 rounded-full bg-white shadow"
              animate={{ x: sound ? 22 : 2 }}
              transition={{ type: 'spring', stiffness: 380, damping: 28 }}
            />
          </button>
        </div>
      </Section>
    </div>
  );
}

function Section({
  title,
  description,
  icon: Icon,
  children,
}: {
  title: string;
  description?: string;
  icon: typeof Sun;
  children: React.ReactNode;
}) {
  return (
    <section>
      <header className="mb-3 flex items-start gap-3">
        <div className="grid h-9 w-9 place-items-center rounded-lg bg-brand-500/10 text-brand-600">
          <Icon className="h-4 w-4" aria-hidden="true" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-ink">{title}</h3>
          {description && <p className="text-xs text-ink-muted">{description}</p>}
        </div>
      </header>
      {children}
    </section>
  );
}

function SegmentCard({
  selected,
  onClick,
  label,
  icon: Icon,
}: {
  selected: boolean;
  onClick: () => void;
  label: string;
  icon: typeof Sun;
}) {
  return (
    <motion.button
      type="button"
      whileHover={{ y: -2 }}
      whileTap={{ scale: 0.97 }}
      onClick={onClick}
      className={`flex items-center justify-center gap-2 rounded-xl border px-3 py-2.5 text-sm font-medium transition ${
        selected
          ? 'border-brand-500 bg-brand-500/10 text-brand-700 dark:text-brand-300'
          : 'border-border bg-surface-elevated text-ink hover:border-ink-subtle'
      }`}
      aria-pressed={selected}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      {label}
    </motion.button>
  );
}
