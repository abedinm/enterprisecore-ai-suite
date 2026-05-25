/**
 * Locale-aware formatters. Thin wrappers over the `Intl.*` APIs so the rest
 * of the app never hard-codes `en-US` patterns. Each helper falls back to
 * the active i18next language when no explicit locale is passed.
 */
import i18n from '../i18n';

function active(locale?: string | null): string {
  return locale || i18n.language || 'en';
}

/** Currency amount → localized string (e.g. "$1,234.50", "1.234,50 €"). */
export function formatCurrency(
  amount: number | null | undefined,
  currency: string = 'USD',
  locale?: string,
): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return '—';
  try {
    return new Intl.NumberFormat(active(locale), {
      style: 'currency',
      currency: currency || 'USD',
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(2)}`;
  }
}

/** Date → localized medium-style string. Accepts Date, ISO string, epoch ms. */
export function formatDate(
  value: Date | string | number | null | undefined,
  locale?: string,
  options: Intl.DateTimeFormatOptions = { year: 'numeric', month: 'short', day: '2-digit' },
): string {
  if (value === null || value === undefined || value === '') return '—';
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  try {
    return new Intl.DateTimeFormat(active(locale), options).format(d);
  } catch {
    return d.toISOString().slice(0, 10);
  }
}

/** Date+time → localized string. */
export function formatDateTime(
  value: Date | string | number | null | undefined,
  locale?: string,
): string {
  return formatDate(value, locale, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Plain number → localized digit grouping (e.g. "1,234" / "1.234"). */
export function formatNumber(
  num: number | null | undefined,
  locale?: string,
  options?: Intl.NumberFormatOptions,
): string {
  if (num === null || num === undefined || Number.isNaN(num)) return '—';
  try {
    return new Intl.NumberFormat(active(locale), options).format(num);
  } catch {
    return String(num);
  }
}

/** Relative time ("3 hours ago", "in 5 minutes") from a target date. */
export function relativeTime(
  value: Date | string | number | null | undefined,
  locale?: string,
): string {
  if (value === null || value === undefined || value === '') return '';
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  const diffMs = d.getTime() - Date.now();
  const absSec = Math.round(Math.abs(diffMs) / 1000);
  const sign = diffMs >= 0 ? 1 : -1;
  // Pick the largest sensible unit.
  const buckets: [Intl.RelativeTimeFormatUnit, number][] = [
    ['year',   60 * 60 * 24 * 365],
    ['month',  60 * 60 * 24 * 30],
    ['week',   60 * 60 * 24 * 7],
    ['day',    60 * 60 * 24],
    ['hour',   60 * 60],
    ['minute', 60],
    ['second', 1],
  ];
  let unit: Intl.RelativeTimeFormatUnit = 'second';
  let count = absSec;
  for (const [u, s] of buckets) {
    if (absSec >= s) {
      unit = u;
      count = Math.round(absSec / s);
      break;
    }
  }
  try {
    return new Intl.RelativeTimeFormat(active(locale), { numeric: 'auto' })
      .format(sign * count, unit);
  } catch {
    return d.toISOString();
  }
}
