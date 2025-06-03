// Basic Playwright configuration for e2e tests
// See https://playwright.dev/docs/test-intro

/** @type {import('@playwright/test').PlaywrightTestConfig} */
const config = {
  webServer: {
    command: 'python main.py',
    port: 5000,
    // Short timeout to avoid hanging CI jobs
    timeout: 10 * 1000,
    reuseExistingServer: true,
  },
  use: {
    baseURL: 'http://localhost:5000',
    headless: true,
  },
};

module.exports = config;
