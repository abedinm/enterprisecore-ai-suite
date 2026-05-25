import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './locales/en.json';
import es from './locales/es.json';
import fr from './locales/fr.json';
import de from './locales/de.json';
import pt from './locales/pt.json';
import it from './locales/it.json';
import ja from './locales/ja.json';
import zh from './locales/zh.json';
import ar from './locales/ar.json';
import he from './locales/he.json';
import ur from './locales/ur.json';

export type SupportedLocale =
  | 'en' | 'es' | 'fr' | 'de' | 'pt' | 'it' | 'ja' | 'zh' | 'ar' | 'he' | 'ur';

export const SUPPORTED_LOCALES: { code: SupportedLocale; name: string; native: string; rtl?: boolean }[] = [
  { code: 'en', name: 'English',    native: 'English' },
  { code: 'es', name: 'Spanish',    native: 'Español' },
  { code: 'fr', name: 'French',     native: 'Français' },
  { code: 'de', name: 'German',     native: 'Deutsch' },
  { code: 'pt', name: 'Portuguese', native: 'Português' },
  { code: 'it', name: 'Italian',    native: 'Italiano' },
  { code: 'ja', name: 'Japanese',   native: '日本語' },
  { code: 'zh', name: 'Chinese',    native: '中文' },
  { code: 'ar', name: 'Arabic',     native: 'العربية', rtl: true },
  { code: 'he', name: 'Hebrew',     native: 'עברית',   rtl: true },
  { code: 'ur', name: 'Urdu',       native: 'اردو',    rtl: true },
];

export const RTL_LOCALES: ReadonlySet<SupportedLocale> = new Set(['ar', 'he', 'ur']);

export function isRTL(locale: string | undefined | null): boolean {
  if (!locale) return false;
  return RTL_LOCALES.has(locale.slice(0, 2) as SupportedLocale);
}

/** Apply <html lang> + <html dir> attributes for the active locale. */
export function applyDocumentLocale(locale: string) {
  if (typeof document === 'undefined') return;
  const code = (locale || 'en').slice(0, 2);
  document.documentElement.lang = code;
  document.documentElement.dir = isRTL(code) ? 'rtl' : 'ltr';
}

const stored = (typeof localStorage !== 'undefined' && localStorage.getItem('ec.locale')) || 'en';

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      es: { translation: es },
      fr: { translation: fr },
      de: { translation: de },
      pt: { translation: pt },
      it: { translation: it },
      ja: { translation: ja },
      zh: { translation: zh },
      ar: { translation: ar },
      he: { translation: he },
      ur: { translation: ur },
    },
    lng: stored,
    fallbackLng: 'en',
    interpolation: { escapeValue: false },
  });

// Apply <html lang/dir> immediately + whenever the language changes.
applyDocumentLocale(i18n.language);
i18n.on('languageChanged', (lng) => applyDocumentLocale(lng));

export default i18n;
