import { test, expect } from '@playwright/test';

test('login renders grid', async ({ page }) => {
  await page.goto('/login');
  await page.fill('input[name="username"]', 'e2e');
  await page.fill('input[name="password"]', 'secret');
  await page.click('input[type="submit"]');
  await expect(page).toHaveURL('/');
  await expect(page.locator('#template-list')).toBeVisible();
});
