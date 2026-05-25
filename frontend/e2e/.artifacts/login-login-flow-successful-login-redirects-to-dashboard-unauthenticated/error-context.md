# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: login.spec.ts >> login flow >> successful login redirects to dashboard
- Location: e2e\login.spec.ts:25:3

# Error details

```
Error: expect(page).toHaveURL(expected) failed

Expected pattern: /#\/$/
Received string:  "http://127.0.0.1:4173/#/login"
Timeout: 20000ms

Call log:
  - Expect "toHaveURL" with timeout 20000ms
    43 × unexpected value "http://127.0.0.1:4173/#/login"

```

```yaml
- img
- paragraph: EnterpriseCore AI Suite
- paragraph: Offline-first business command center
- heading "Sign in" [level=1]
- paragraph: Welcome back. Enter your credentials to continue.
- text: Email
- textbox "Email": admin@local
- text: Password
- textbox "Password": ChangeMe123!
- paragraph: Could not sign in. Check the backend is running on http://127.0.0.1:8765.
- button "Sign in":
  - img
  - text: Sign in
- paragraph:
  - text: No account?
  - link "Create one":
    - /url: "#/register"
- paragraph: "Default admin: admin@local / ChangeMe123!"
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | test.describe('login flow', () => {
  4  |   test('form validates required fields', async ({ page }) => {
  5  |     await page.goto('/#/login');
  6  |     // Clear the default prefilled values to exercise the required-field path.
  7  |     await page.getByLabel(/email/i).fill('');
  8  |     await page.getByLabel(/password/i).fill('');
  9  |     await page.getByRole('button', { name: /sign in/i }).click();
  10 |     // HTML5 validation kicks in: the email input must be focused/invalid and
  11 |     // the URL should still be /login (no navigation).
  12 |     await expect(page).toHaveURL(/#\/login$/);
  13 |   });
  14 | 
  15 |   test('rejects wrong password', async ({ page }) => {
  16 |     await page.goto('/#/login');
  17 |     await page.getByLabel(/email/i).fill('admin@local');
  18 |     await page.getByLabel(/password/i).fill('definitely-wrong-password-12345');
  19 |     await page.getByRole('button', { name: /sign in/i }).click();
  20 |     // The auth store surfaces the backend error via setError → the rose alert.
  21 |     await expect(page.locator('p.text-rose-600, p.dark\\:text-rose-300').first()).toBeVisible({ timeout: 15_000 });
  22 |     await expect(page).toHaveURL(/#\/login$/);
  23 |   });
  24 | 
  25 |   test('successful login redirects to dashboard', async ({ page }) => {
  26 |     await page.goto('/#/login');
  27 |     await page.getByLabel(/email/i).fill('admin@local');
  28 |     await page.getByLabel(/password/i).fill('ChangeMe123!');
  29 |     await page.getByRole('button', { name: /sign in/i }).click();
> 30 |     await expect(page).toHaveURL(/#\/$/, { timeout: 20_000 });
     |                        ^ Error: expect(page).toHaveURL(expected) failed
  31 |     await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible();
  32 |   });
  33 | });
  34 | 
```