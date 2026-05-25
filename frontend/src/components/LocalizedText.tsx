/**
 * LocalizedText — wraps inline text that's in a language other than the
 * surrounding document. Helps screen readers switch pronunciation rules
 * for that snippet (WCAG 3.1.2).
 *
 *   <LocalizedText lang="es">Buenos días</LocalizedText>
 *   <LocalizedText lang="fr" as="p">Bienvenue</LocalizedText>
 */
import { createElement, type ReactNode } from 'react';

export type LocalizedTextProps = {
  lang: string;
  /** Tag to render. Defaults to <span>. */
  as?: keyof JSX.IntrinsicElements;
  className?: string;
  children: ReactNode;
};

export function LocalizedText({ lang, as = 'span', className, children }: LocalizedTextProps) {
  return createElement(as, { lang, className }, children);
}
