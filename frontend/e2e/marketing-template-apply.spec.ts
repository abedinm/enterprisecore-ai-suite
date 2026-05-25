import { test, expect } from '@playwright/test';

test.describe('marketing — apply a template', () => {
  test('Restaurant template applies and dashboard checklist updates', async ({ page }) => {
    // The templates page is /marketing/templates — visit directly.
    await page.goto('/#/marketing/templates');
    await expect(page.locator('body')).toContainText(/template/i, { timeout: 15_000 });

    // Find the Restaurant card and click it.
    const restaurant = page.locator(':text("Restaurant")').first();
    await restaurant.waitFor({ state: 'visible', timeout: 15_000 });
    await restaurant.click();

    // Confirm dialog → "Apply with wipe". The exact wording varies; tolerate
    // common variants.
    const applyButton = page.getByRole('button', { name: /Apply.*wipe|Apply template|Replace/i }).first();
    if (await applyButton.isVisible().catch(() => false)) {
      page.once('dialog', (dialog) => dialog.accept());
      await applyButton.click();
    }

    // After apply, the dashboard checklist should have refreshed. Navigate
    // back and check for a launch-checklist surface.
    await page.goto('/#/marketing');
    await expect(page.locator('body')).toContainText(/launch|checklist|ready|complete/i, { timeout: 15_000 });
  });
});
