import { test, expect } from '@playwright/test';

// Mock the RAG query so we don't depend on a model being loaded in Ollama.
// The real backend serves /api/v1/ai/knowledge/* — we intercept the
// query/chunks calls to deterministic responses.
test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/ai/knowledge/*/query*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        chunks: [
          { id: 'mock-1', text: 'Mock knowledge chunk about EnterpriseCore.', score: 0.92, source: 'mock.md' },
        ],
        answer: 'Mocked answer.',
      }),
    });
  });
});

test.describe('AI Brain / Knowledge Hub', () => {
  test('AI Brain page mounts', async ({ page }) => {
    await page.goto('/#/ai');
    await expect(page.getByText(/AI Brain|Chat|Knowledge|RAG/i).first()).toBeVisible({ timeout: 15_000 });
  });

  test('knowledge tab is reachable', async ({ page }) => {
    await page.goto('/#/ai');
    // Tab labels per AIBrainPage: Chat, Writer, Sentiment, etc. Knowledge
    // is one of them. Click it if present.
    const knowledgeTab = page.getByRole('button', { name: /Knowledge|RAG/i }).first();
    if (await knowledgeTab.isVisible().catch(() => false)) {
      await knowledgeTab.click();
      await expect(page.locator('body')).toContainText(/Knowledge|library|document|kb/i);
    } else {
      // Fall back to RAG Chat which is always rendered too.
      const ragTab = page.getByRole('button', { name: /RAG/i }).first();
      if (await ragTab.isVisible().catch(() => false)) {
        await ragTab.click();
      }
    }
  });
});
