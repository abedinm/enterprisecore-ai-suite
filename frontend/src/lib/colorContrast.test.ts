import { describe, expect, it } from 'vitest';
import { AA_NORMAL, autoAdjust, contrastRatio, meetsAA, parseHex } from './colorContrast';

describe('colorContrast', () => {
  it('parses 3- and 6-digit hex', () => {
    expect(parseHex('#fff')).toEqual({ r: 255, g: 255, b: 255 });
    expect(parseHex('000')).toEqual({ r: 0, g: 0, b: 0 });
    expect(parseHex('#4f46e5')).toEqual({ r: 79, g: 70, b: 229 });
  });

  it('returns null for malformed hex', () => {
    expect(parseHex('not-a-color')).toBeNull();
    expect(parseHex('')).toBeNull();
  });

  it('computes contrast ratio of 21 for black on white', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 0);
  });

  it('computes contrast ratio of 1 for identical colors', () => {
    expect(contrastRatio('#888', '#888')).toBeCloseTo(1, 1);
  });

  it('meetsAA passes for high-contrast pairs and fails for low-contrast', () => {
    expect(meetsAA('#000', '#fff')).toBe(true);
    expect(meetsAA('#ccc', '#fff')).toBe(false);
  });

  it('autoAdjust returns a color that meets AA on a light background', () => {
    const adjusted = autoAdjust('#ffd966', '#ffffff');
    expect(contrastRatio(adjusted, '#ffffff')).toBeGreaterThanOrEqual(AA_NORMAL);
  });
});
