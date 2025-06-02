import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/playwright',
  use: { baseURL: 'http://127.0.0.1:5000', headless: true },
  webServer: {
    command: 'python scripts/start_playwright_server.py',
    port: 5000,
    timeout: 60000,
    reuseExistingServer: !process.env.CI,
  },
});
