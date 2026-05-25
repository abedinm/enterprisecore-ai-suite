# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: marketing-public-site.spec.ts >> marketing public site >> sitemap.xml is served as valid XML
- Location: e2e\marketing-public-site.spec.ts:16:3

# Error details

```
Error: apiRequestContext.get: connect ECONNREFUSED 127.0.0.1:8765
Call log:
  - → GET http://127.0.0.1:8765/site/sitemap.xml
    - user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.7778.96 Safari/537.36
    - accept: */*
    - accept-encoding: gzip,deflate,br

```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | // The /site/* routes are PUBLIC — no auth required. We hit the backend
  4  | // directly via the vite proxy or in production via the same origin.
  5  | const BACKEND_URL = process.env.E2E_BACKEND_URL ?? 'http://127.0.0.1:8765';
  6  | 
  7  | test.describe('marketing public site', () => {
  8  |   test('homepage renders Meridian content', async ({ page }) => {
  9  |     const response = await page.goto(`${BACKEND_URL}/site/`);
  10 |     expect(response?.status()).toBeLessThan(400);
  11 |     // The Meridian seed has the company name in the hero — verify SOMETHING
  12 |     // related to the marketing site renders (heading, nav, or branded text).
  13 |     await expect(page.locator('body')).toContainText(/Meridian|Marketing|Welcome/i, { timeout: 10_000 });
  14 |   });
  15 | 
  16 |   test('sitemap.xml is served as valid XML', async ({ request }) => {
> 17 |     const response = await request.get(`${BACKEND_URL}/site/sitemap.xml`);
     |                                    ^ Error: apiRequestContext.get: connect ECONNREFUSED 127.0.0.1:8765
  18 |     expect(response.status()).toBe(200);
  19 |     const contentType = response.headers()['content-type'] ?? '';
  20 |     expect(contentType).toMatch(/xml/i);
  21 |     const body = await response.text();
  22 |     expect(body).toContain('<urlset');
  23 |     expect(body).toMatch(/<\/urlset>/);
  24 |   });
  25 | });
  26 | 
```