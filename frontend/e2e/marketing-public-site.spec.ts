import { test, expect } from '@playwright/test';

// The /site/* routes are PUBLIC — no auth required. We hit the backend
// directly via the vite proxy or in production via the same origin.
const BACKEND_URL = process.env.E2E_BACKEND_URL ?? 'http://127.0.0.1:8765';

test.describe('marketing public site', () => {
  test('homepage renders Meridian content', async ({ page }) => {
    const response = await page.goto(`${BACKEND_URL}/site/`);
    expect(response?.status()).toBeLessThan(400);
    // The Meridian seed has the company name in the hero — verify SOMETHING
    // related to the marketing site renders (heading, nav, or branded text).
    await expect(page.locator('body')).toContainText(/Meridian|Marketing|Welcome/i, { timeout: 10_000 });
  });

  test('sitemap.xml is served as valid XML', async ({ request }) => {
    const response = await request.get(`${BACKEND_URL}/site/sitemap.xml`);
    expect(response.status()).toBe(200);
    const contentType = response.headers()['content-type'] ?? '';
    expect(contentType).toMatch(/xml/i);
    const body = await response.text();
    expect(body).toContain('<urlset');
    expect(body).toMatch(/<\/urlset>/);
  });
});
