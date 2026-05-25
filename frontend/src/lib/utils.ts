import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import {
  formatCurrency as _fmtCurrency,
  formatDate as _fmtDate,
  formatDateTime as _fmtDateTime,
  formatNumber as _fmtNumber,
  relativeTime as _relTime,
} from './format';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Legacy wrappers — delegate to ./format so values track the active i18n
// locale instead of being pinned to the browser default. Callers keep the
// same `(string | number)` input shape they always had.
export function formatNumber(n: number | string | null | undefined): string {
  if (n === null || n === undefined || n === '') return '—';
  const v = typeof n === 'string' ? parseFloat(n) : n;
  return _fmtNumber(v, undefined, { maximumFractionDigits: 2 });
}

export function formatCurrency(amount: number | string | null | undefined, currency = 'USD'): string {
  if (amount === null || amount === undefined || amount === '') return '—';
  const value = typeof amount === 'string' ? parseFloat(amount) : amount;
  return _fmtCurrency(value, currency);
}

export function formatDate(d: string | Date | null | undefined): string {
  return _fmtDate(d ?? null);
}

export function formatDateTime(d: string | Date | null | undefined): string {
  return _fmtDateTime(d ?? null);
}

export function relativeTime(d: string | Date | null | undefined): string {
  if (!d) return '—';
  return _relTime(d) || '—';
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
