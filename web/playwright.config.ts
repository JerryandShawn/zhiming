import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/e2e',
  testIgnore: [
    /contracts\.spec\.ts/,
    /live-visual\.spec\.ts/,
    /spaces.*\.spec\.ts/,
    /components.*\.spec\.ts/,
    /night-.*\.spec\.ts/,
  ],
  timeout: 60000,
  fullyParallel: false,
  workers: 1,
  outputDir: 'test-results/static-runs',
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    channel: process.env.CI ? undefined : 'chrome',
    headless: true,
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    reducedMotion: 'reduce',
    trace: 'retain-on-failure',
  },
  webServer: { command: 'npm run preview', url: 'http://127.0.0.1:4173', reuseExistingServer: true },
});
