import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'v4-base.spec.ts',
  timeout: 60000,
  workers: 1,
  outputDir: 'test-results/v4-base-runs',
  reporter: [['list'], ['json', { outputFile: 'test-results/v4-base-evidence/playwright.json' }]],
  use: {
    channel: process.env.CI ? undefined : 'chrome',
    headless: true,
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    reducedMotion: 'reduce',
    trace: 'retain-on-failure',
  },
});
