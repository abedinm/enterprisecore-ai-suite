import { test, expect } from '@playwright/test';

test.describe('construction — create a new project', () => {
  test('fill new-project form and confirm it appears in the list', async ({ page }) => {
    await page.goto('/#/construction');
    await expect(page.getByRole('heading', { name: /Construction/i }).first()).toBeVisible({ timeout: 15_000 });

    // Open the new-project form. The list page uses a "New project" CTA.
    const newButton = page.getByRole('button', { name: /New project|\+ New|Add project/i }).first();
    if (!(await newButton.isVisible().catch(() => false))) {
      // Older builds might use a link with the same label.
      const newLink = page.getByRole('link', { name: /New project/i }).first();
      await newLink.click();
    } else {
      await newButton.click();
    }

    // The form is a modal/inline form — locate the Name input by label.
    const nameInput = page.getByLabel(/Project name|^Name/i).first();
    await nameInput.waitFor({ state: 'visible', timeout: 10_000 });
    const projectName = `E2E Smoke ${Date.now()}`;
    await nameInput.fill(projectName);

    const client = page.getByLabel(/client/i).first();
    if (await client.isVisible().catch(() => false)) {
      await client.fill('Playwright Client Co.');
    }
    const location = page.getByLabel(/location/i).first();
    if (await location.isVisible().catch(() => false)) {
      await location.fill('Localhost, IDE');
    }

    // Submit.
    await page.getByRole('button', { name: /^Create$|Save|Submit/i }).first().click();

    // After save, navigate back to the list view and verify the project shows.
    await page.goto('/#/construction');
    await expect(page.getByText(projectName)).toBeVisible({ timeout: 15_000 });
  });
});
