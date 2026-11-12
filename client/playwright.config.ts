import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  timeout: 45_000,
  use: { baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:5173', browserName: 'chromium', screenshot: 'only-on-failure', trace: 'retain-on-failure' },
});
