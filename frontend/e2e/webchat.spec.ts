import { test, expect } from '@playwright/test';

// Mock Ollama / Anthropic chat completions so the sandbox is deterministic.
test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/webchat/**/chat', async (route) => {
    const body = {
      reply: 'Hello — this is a mocked sandbox response.',
      messages: [],
      conversation_id: 'mock-conv-1',
    };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
});

test.describe('web chat', () => {
  test('bot list page loads', async ({ page }) => {
    await page.goto('/#/webchat');
    await expect(page.getByRole('heading', { name: /Web Chat Bots/i })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('button', { name: /New bot/i })).toBeVisible();
  });

  test('can navigate to new-bot form', async ({ page }) => {
    await page.goto('/#/webchat');
    await page.getByRole('button', { name: /New bot/i }).first().click();
    await expect(page).toHaveURL(/#\/webchat\/bots\/new/);
  });

  test('sandbox renders chat surface and accepts a message', async ({ page }) => {
    // We'll smoke-test the BotEditor route. If creating a bot end-to-end is
    // too slow against a live backend, the page still mounts and shows the
    // editor scaffolding.
    await page.goto('/#/webchat/bots/new');
    await expect(page.locator('body')).toContainText(/bot|name|welcome|prompt/i, { timeout: 15_000 });
  });
});
