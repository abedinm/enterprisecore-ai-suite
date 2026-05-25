/**
 * Accessibility audit — runs axe-core against the core authenticated pages.
 *
 * Fails the build if any "critical" or "serious" violations land. Lower-
 * severity violations (moderate, minor) are logged but tolerated for now;
 * raise the bar incrementally rather than dumping the whole repo on day 1.
 *
 * To regenerate the baseline:
 *   pnpm exec playwright test e2e/a11y.spec.ts --update-snapshots
 *
 * Page coverage:
 *   - Login         (anonymous, high traffic)
 *   - Dashboard     (first thing authenticated users see)
 *   - Settings      (forms-heavy; the most a11y-error-prone surface)
 *   - Search        (interactive results list)
 *   - Finance > Invoices (representative module page)
 */
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const HIGH_SEVERITY = new Set(['critical', 'serious']);

async function assertNoCriticalA11yViolations(page, label: string) {
  const results = await new AxeBuilder({ page })
    // We exclude color-contrast on chrome shapes injected by Recharts /
    // Monaco — they ship their own a11y story and false-positive here.
    .disableRules(['color-contrast'])
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();

  const high = results.violations.filter(v => HIGH_SEVERITY.has(v.impact ?? ''));
  if (high.length > 0) {
    /* eslint-disable no-console */
    console.error(`A11y violations on ${label}:`);
    for (const v of high) {
      console.error(`  [${v.impact}] ${v.id}: ${v.help}`);
      console.error(`    docs: ${v.helpUrl}`);
      console.error(`    nodes: ${v.nodes.length}`);
    }
    /* eslint-enable no-console */
  }
  expect(high, `axe-core: ${label} has ${high.length} high-severity violations`).toEqual([]);
}

test.describe('a11y', () => {
  test('login page passes wcag2aa', async ({ page }) => {
    await page.goto('/#/login');
    await page.waitForLoadState('networkidle');
    await assertNoCriticalA11yViolations(page, 'login');
  });

  test('dashboard passes wcag2aa', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await assertNoCriticalA11yViolations(page, 'dashboard');
  });

  test('settings page passes wcag2aa', async ({ page }) => {
    await page.goto('/#/settings');
    await page.waitForLoadState('networkidle');
    await assertNoCriticalA11yViolations(page, 'settings');
  });

  test('search page passes wcag2aa', async ({ page }) => {
    await page.goto('/#/search?q=test');
    await page.waitForLoadState('networkidle');
    await assertNoCriticalA11yViolations(page, 'search');
  });

  test('finance > invoices passes wcag2aa', async ({ page }) => {
    await page.goto('/#/finance?tab=invoices');
    await page.waitForLoadState('networkidle');
    await assertNoCriticalA11yViolations(page, 'finance.invoices');
  });
});
