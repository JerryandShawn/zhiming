import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/legacy-e2e',
  timeout: 45000,
  fullyParallel: false,
  workers: 2,
  outputDir: 'test-results/legacy-browser-first',
  reporter: [['list']],
  use: {
    channel: process.env.CI ? undefined : 'chrome',
    headless: true,
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    reducedMotion: 'reduce',
    trace: 'retain-on-failure',
  },
});
