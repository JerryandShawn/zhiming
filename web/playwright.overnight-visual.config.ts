import { defineConfig } from '@playwright/test';

process.env.MINGJING_OVERNIGHT_RUN_ID ??= new Date().toISOString();
const batch = process.env.MINGJING_OVERNIGHT_RUN_ID.replace(/[^a-zA-Z0-9-]/g, '-');
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'overnight-matrix.spec.ts',
  timeout: 45000,
  workers: 2,
  outputDir: `test-results/overnight/${batch}`,
  reporter: [['list'], ['json', { outputFile: `test-results/overnight/${batch}/report.json` }]],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    channel: process.env.CI ? undefined : 'chrome',
    headless: true,
    locale: 'zh-CN',
    timezoneId: 'Asia/Taipei',
    reducedMotion: 'reduce',
    deviceScaleFactor: 1,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: { command: 'npm run preview', url: 'http://127.0.0.1:4173', reuseExistingServer: true },
});
