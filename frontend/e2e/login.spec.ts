import { test, expect } from '@playwright/test';

test.describe('login flow', () => {
  test('form validates required fields', async ({ page }) => {
    await page.goto('/#/login');
    // Clear the default prefilled values to exercise the required-field path.
    await page.getByLabel(/email/i).fill('');
    await page.getByLabel(/password/i).fill('');
    await page.getByRole('button', { name: /sign in/i }).click();
    // HTML5 validation kicks in: the email input must be focused/invalid and
    // the URL should still be /login (no navigation).
    await expect(page).toHaveURL(/#\/login$/);
  });

  test('rejects wrong password', async ({ page }) => {
    await page.goto('/#/login');
    await page.getByLabel(/email/i).fill('admin@local');
    await page.getByLabel(/password/i).fill('definitely-wrong-password-12345');
    await page.getByRole('button', { name: /sign in/i }).click();
    // The auth store surfaces the backend error via setError → the rose alert.
    await expect(page.locator('p.text-rose-600, p.dark\\:text-rose-300').first()).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveURL(/#\/login$/);
  });

  test('successful login redirects to dashboard', async ({ page }) => {
    await page.goto('/#/login');
    await page.getByLabel(/email/i).fill('admin@local');
    await page.getByLabel(/password/i).fill('ChangeMe123!');
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page).toHaveURL(/#\/$/, { timeout: 20_000 });
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible();
  });
});
