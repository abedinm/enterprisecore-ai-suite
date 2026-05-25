import { defineConfig, devices } from '@playwright/test';

// The E2E suite runs against a live Vite dev server in development, and against
// `vite preview` in CI (production build, same code that ships in the Electron
// installer). The backend must already be running on 127.0.0.1:8765 — we don't
// spawn it here because it owns its own SQLite DB, ports, and seed data.

const PORT = Number(process.env.E2E_PORT ?? 5173);
const BASE_URL = process.env.E2E_BASE_URL ?? `http://127.0.0.1:${PORT}`;
const IS_CI = !!process.env.CI;
const USE_PREVIEW = process.env.E2E_USE_PREVIEW === '1' || IS_CI;

export default defineConfig({
  testDir: './e2e',
  outputDir: './e2e/.artifacts',
  fullyParallel: true,
  forbidOnly: IS_CI,
  retries: IS_CI ? 2 : 0,
  workers: IS_CI ? 4 : 1,
  reporter: IS_CI ? [['list'], ['html', { outputFolder: 'e2e/playwright-report', open: 'never' }]] : 'list',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  webServer: USE_PREVIEW
    ? {
        command: `npm run preview -- --host 127.0.0.1 --port ${PORT} --strictPort`,
        url: BASE_URL,
        reuseExistingServer: !IS_CI,
        timeout: 120_000,
      }
    : {
        command: `npm run dev -- --host 127.0.0.1 --port ${PORT} --strictPort`,
        url: BASE_URL,
        reuseExistingServer: !IS_CI,
        timeout: 120_000,
      },
  projects: [
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'e2e/.auth/admin.json',
      },
      dependencies: ['setup'],
      testIgnore: [/auth\.setup\.ts/, /login\.spec\.ts/, /marketing-public-site\.spec\.ts/],
    },
    {
      name: 'unauthenticated',
      use: { ...devices['Desktop Chrome'] },
      testMatch: [/login\.spec\.ts/, /marketing-public-site\.spec\.ts/],
    },
  ],
});
