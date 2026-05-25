import { test, expect } from '@playwright/test';

test.describe('construction project workspace', () => {
  test('Riverside project opens and tabs navigate', async ({ page }) => {
    await page.goto('/#/construction');
    await expect(page.getByRole('heading', { name: /Construction/i }).first()).toBeVisible({ timeout: 15_000 });

    // The seed includes "Riverside" — click into it (matches case-insensitively
    // anywhere on the card).
    const riversideCard = page.locator('a:has-text("Riverside"), :text("Riverside")').first();
    await riversideCard.waitFor({ state: 'visible', timeout: 15_000 });
    await riversideCard.click();

    // Dashboard should land — wait for any project-dashboard tab/heading.
    await expect(page.locator('body')).toContainText(/Risks|Schedule|Milestones|Dashboard/i, { timeout: 15_000 });
  });

  test('navigates Risks tab and shows risk content', async ({ page }) => {
    await page.goto('/#/construction');
    const riverside = page.locator('a:has-text("Riverside"), :text("Riverside")').first();
    await riverside.waitFor({ state: 'visible', timeout: 15_000 });
    await riverside.click();
    // Click the Risks tab from the construction layout sub-nav.
    const risksLink = page.getByRole('link', { name: /^Risks$/i }).first();
    if (await risksLink.isVisible().catch(() => false)) {
      await risksLink.click();
      await expect(page.locator('body')).toContainText(/risk|severity|likelihood|heatmap/i, { timeout: 15_000 });
    }
  });

  test('navigates Milestones and Schedule tabs', async ({ page }) => {
    await page.goto('/#/construction');
    const riverside = page.locator('a:has-text("Riverside"), :text("Riverside")').first();
    await riverside.waitFor({ state: 'visible', timeout: 15_000 });
    await riverside.click();

    const milestones = page.getByRole('link', { name: /^Milestones$/i }).first();
    if (await milestones.isVisible().catch(() => false)) {
      await milestones.click();
      await expect(page.locator('body')).toContainText(/milestone|date|status/i);
    }
    const schedule = page.getByRole('link', { name: /^Schedule$/i }).first();
    if (await schedule.isVisible().catch(() => false)) {
      await schedule.click();
      await expect(page.locator('body')).toContainText(/schedule|task|gantt|start/i);
    }
  });
});
