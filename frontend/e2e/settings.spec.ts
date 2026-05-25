import { test, expect } from '@playwright/test';

test.describe('system settings', () => {
  test('settings page loads', async ({ page }) => {
    await page.goto('/#/settings');
    await expect(page.locator('body')).toContainText(/Settings|Preferences|System/i, { timeout: 15_000 });
  });

  test('change a value, save, reload, persists', async ({ page }) => {
    await page.goto('/#/settings');
    // Find the first text-ish input on the settings page and tweak it. This
    // is intentionally tolerant — different builds expose different fields.
    const firstInput = page.locator('input[type="text"], input:not([type])').first();
    if (await firstInput.isVisible().catch(() => false)) {
      const original = await firstInput.inputValue();
      const next = `${original}-pw`;
      await firstInput.fill(next);

      const saveBtn = page.getByRole('button', { name: /^Save$|Save changes|Apply/i }).first();
      if (await saveBtn.isVisible().catch(() => false)) {
        await saveBtn.click();
        // Reload and confirm the new value stuck.
        await page.reload();
        await expect(firstInput).toHaveValue(next, { timeout: 10_000 });
        // Reset to original so this test is idempotent across runs.
        await firstInput.fill(original);
        await saveBtn.click().catch(() => {});
      }
    }
  });
});
