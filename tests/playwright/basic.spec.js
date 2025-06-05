// tests/playwright/basic.spec.js
// Minimal Playwright test covering login and dashboard load
const { test, expect } = require('@playwright/test');

test('index redirects to login', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/login$/);
});

// This test assumes a user exists with username 'e2e' and password 'secret'.
// It mirrors the Python Selenium test and ensures the dashboard loads.
test('login and open dashboard', async ({ page }) => {
  await page.goto('/login');
  await page.fill('input[name="username"]', 'e2e');
  await page.fill('input[name="password"]', 'secret');
  await page.click('input[type="submit"]');
  await expect(page).toHaveURL('/');
  await expect(page.locator('#search-input')).toBeVisible();
});
