import { test, expect } from '@playwright/test';

test('nav links work', async ({ page }) => {
  await page.goto('/login');
  await page.fill('input[name="username"]', 'e2e');
  await page.fill('input[name="password"]', 'secret');
  await page.click('input[type="submit"]');

  await page.click('a[href="/settings"]');
  await expect(page).toHaveURL('/settings');

  await page.click('a[title="Home"]');
  await expect(page).toHaveURL('/');
});
