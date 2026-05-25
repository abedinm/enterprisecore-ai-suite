/**
 * WCAG 2.x relative-luminance and contrast-ratio helpers.
 *
 * Implements the formula at https://www.w3.org/TR/WCAG21/#dfn-relative-luminance
 * and https://www.w3.org/TR/WCAG21/#dfn-contrast-ratio.
 *
 * `contrastRatio('#fff', '#000')` returns 21.
 */

export type Rgb = { r: number; g: number; b: number };

const HEX_SHORT = /^#?([\da-f])([\da-f])([\da-f])$/i;
const HEX_LONG = /^#?([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i;

/** Parse a CSS hex color into 0-255 RGB. Returns null if the input is malformed. */
export function parseHex(input: string): Rgb | null {
  if (!input) return null;
  const short = input.match(HEX_SHORT);
  if (short) {
    return {
      r: parseInt(short[1] + short[1], 16),
      g: parseInt(short[2] + short[2], 16),
      b: parseInt(short[3] + short[3], 16),
    };
  }
  const long = input.match(HEX_LONG);
  if (long) {
    return {
      r: parseInt(long[1], 16),
      g: parseInt(long[2], 16),
      b: parseInt(long[3], 16),
    };
  }
  return null;
}

export function toHex({ r, g, b }: Rgb): string {
  const c = (n: number) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0');
  return `#${c(r)}${c(g)}${c(b)}`;
}

/** WCAG relative luminance for a single sRGB channel (0-255 -> 0-1). */
function channelLuminance(channel: number): number {
  const c = channel / 255;
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

/** WCAG relative luminance of an sRGB color, 0..1. */
export function relativeLuminance({ r, g, b }: Rgb): number {
  return (
    0.2126 * channelLuminance(r) +
    0.7152 * channelLuminance(g) +
    0.0722 * channelLuminance(b)
  );
}

/**
 * WCAG contrast ratio between two colors. Inputs may be `#rgb`, `#rrggbb`
 * or `Rgb`. Returns NaN if either color is unparseable.
 */
export function contrastRatio(fg: string | Rgb, bg: string | Rgb): number {
  const a = typeof fg === 'string' ? parseHex(fg) : fg;
  const b = typeof bg === 'string' ? parseHex(bg) : bg;
  if (!a || !b) return NaN;
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const lighter = Math.max(la, lb);
  const darker = Math.min(la, lb);
  return (lighter + 0.05) / (darker + 0.05);
}

/** WCAG AA threshold for normal-sized body text (4.5:1). */
export const AA_NORMAL = 4.5;
/** WCAG AA threshold for large text (3:1). */
export const AA_LARGE = 3;

export function meetsAA(fg: string | Rgb, bg: string | Rgb, large = false): boolean {
  const r = contrastRatio(fg, bg);
  if (Number.isNaN(r)) return false;
  return r >= (large ? AA_LARGE : AA_NORMAL);
}

/**
 * Nudge `fg` toward whichever endpoint (black or white) increases the
 * contrast ratio against `bg`, until the WCAG AA threshold is met or we
 * give up after `maxSteps`. Returns the original color if it already passes
 * or if no improvement is possible.
 */
export function autoAdjust(
  fg: string,
  bg: string,
  threshold: number = AA_NORMAL,
  maxSteps = 60,
): string {
  const fgRgb = parseHex(fg);
  const bgRgb = parseHex(bg);
  if (!fgRgb || !bgRgb) return fg;
  if (contrastRatio(fgRgb, bgRgb) >= threshold) return fg;
  // Decide direction: if bg is lighter, push fg toward black; else toward white.
  const bgLum = relativeLuminance(bgRgb);
  const towardBlack = bgLum > 0.5;
  const target: Rgb = towardBlack ? { r: 0, g: 0, b: 0 } : { r: 255, g: 255, b: 255 };

  let current = { ...fgRgb };
  for (let step = 0; step < maxSteps; step += 1) {
    // Move ~5% toward the target each step.
    current = {
      r: current.r + (target.r - current.r) * 0.08,
      g: current.g + (target.g - current.g) * 0.08,
      b: current.b + (target.b - current.b) * 0.08,
    };
    if (contrastRatio(current, bgRgb) >= threshold) {
      return toHex(current);
    }
  }
  // Threshold unreachable from this direction — return the endpoint.
  return toHex(target);
}
