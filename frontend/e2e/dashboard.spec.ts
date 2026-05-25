import { test, expect } from '@playwright/test';

test.describe('dashboard', () => {
  test('renders the command center heading + KPIs', async ({ page }) => {
    await page.goto('/');
    // The DashboardPage greets the user — wait for it to land.
    await expect(page.getByText(/Command center/i)).toBeVisible({ timeout: 15_000 });
    // SQLite ready / Local-first chips are always rendered (they don't depend
    // on the dashboard query resolving).
    await expect(page.getByText(/SQLite ready/i)).toBeVisible();
    await expect(page.getByText(/Local-first/i)).toBeVisible();
  });

  test('sidebar lists expected operations modules', async ({ page }) => {
    await page.goto('/');
    const sidebar = page.locator('aside').first();
    await expect(sidebar.getByRole('link', { name: 'Dashboard' })).toBeVisible({ timeout: 15_000 });
    // These four are always part of the evaluation plan per the seed.
    for (const name of ['Finance', 'HR', 'CRM', 'Projects']) {
      await expect(sidebar.getByRole('link', { name })).toBeVisible();
    }
    // Vertical modules — Construction + Marketing are bundled with evaluation;
    // Academic is excluded per the license tier we ship in the seed.
    await expect(sidebar.getByRole('link', { name: 'Construction' })).toBeVisible();
    await expect(sidebar.getByRole('link', { name: 'Marketing' })).toBeVisible();
  });

  test('shows online/offline indicator', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText(/Online|Offline/).first()).toBeVisible({ timeout: 15_000 });
  });
});
