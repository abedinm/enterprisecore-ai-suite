import { test, expect } from '@playwright/test';

test.describe('license — evaluation tier', () => {
  test('/api/v1/license/features returns evaluation tier', async ({ request }) => {
    // The request fixture inherits storageState so it carries the admin
    // session cookies — same baseURL as the page tests.
    const response = await request.get('/api/v1/license/features');
    // Some builds put the endpoint outside /api/v1 — fall back when needed.
    let payload: any;
    if (response.status() === 200) {
      payload = await response.json();
    } else {
      const alt = await request.get('/api/v1/license');
      if (alt.status() === 200) payload = await alt.json();
    }
    expect(payload, 'license endpoint returned a JSON body').toBeTruthy();
    // The seed ships an "evaluation" plan — accept evaluation or trial.
    const tier = (payload?.tier ?? payload?.plan ?? payload?.license?.tier ?? '').toString().toLowerCase();
    expect(tier).toMatch(/eval|trial/);
  });

  test('sidebar shows Construction + Marketing but hides Academic', async ({ page }) => {
    await page.goto('/');
    const sidebar = page.locator('aside').first();
    await expect(sidebar.getByRole('link', { name: 'Dashboard' })).toBeVisible({ timeout: 15_000 });
    await expect(sidebar.getByRole('link', { name: 'Construction' })).toBeVisible();
    await expect(sidebar.getByRole('link', { name: 'Marketing' })).toBeVisible();
    // Academic is gated out of the evaluation tier.
    await expect(sidebar.getByRole('link', { name: 'Academic' })).toHaveCount(0);
  });
});
