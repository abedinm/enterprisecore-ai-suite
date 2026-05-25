/**
 * Top-bar language switcher. Dropdown lists every supported locale with
 * its native name; selecting one immediately applies the change (i18next +
 * <html lang/dir> + localStorage + backend pref).
 */
import { Globe } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { SUPPORTED_LOCALES } from '../i18n';
import { useLocale } from '../hooks/useLocale';
import { cn } from '../lib/utils';

type Props = {
  className?: string;
  /** Compact mode hides the current language label (icon-only). */
  compact?: boolean;
};

export function LocaleSwitcher({ className, compact = false }: Props) {
  const { t } = useTranslation();
  const { locale, setLocale } = useLocale();
  const current = SUPPORTED_LOCALES.find((l) => l.code === locale.slice(0, 2));

  return (
    <label
      className={cn(
        'ec-btn-ghost relative inline-flex cursor-pointer items-center gap-1.5 px-2',
        className,
      )}
      title={t('common.language')}
    >
      <Globe size={16} aria-hidden />
      {!compact ? (
        <span className="hidden text-xs font-medium sm:inline">{current?.native ?? locale}</span>
      ) : null}
      <select
        aria-label={t('common.language')}
        value={locale.slice(0, 2)}
        onChange={(e) => {
          void setLocale(e.target.value);
        }}
        className="absolute inset-0 cursor-pointer appearance-none opacity-0"
        data-testid="locale-switcher"
      >
        {SUPPORTED_LOCALES.map((l) => (
          <option key={l.code} value={l.code}>
            {l.native} ({l.name})
          </option>
        ))}
      </select>
    </label>
  );
}
