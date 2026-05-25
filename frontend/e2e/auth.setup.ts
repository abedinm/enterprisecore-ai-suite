import { test as setup, expect } from '@playwright/test';
import path from 'node:path';

const AUTH_FILE = path.join(__dirname, '.auth', 'admin.json');
const EMAIL = process.env.E2E_ADMIN_EMAIL ?? 'admin@local';
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'ChangeMe123!';

setup('authenticate as admin', async ({ page }) => {
  // Hit the login page directly. The app uses hash routing under file:// for
  // Electron — the dev server's root also serves it.
  await page.goto('/#/login');

  // The default form is prefilled with admin@local/ChangeMe123! but we set it
  // explicitly so the test still works if the seed values change.
  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole('button', { name: /sign in/i }).click();

  // After successful login the app navigates to /#/ and the AppShell renders
  // the sidebar with the Dashboard nav link.
  await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible({ timeout: 20_000 });

  // Save signed-in cookies + localStorage so subsequent specs skip the login.
  await page.context().storageState({ path: AUTH_FILE });
});
