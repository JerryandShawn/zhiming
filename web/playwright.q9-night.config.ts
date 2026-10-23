import { defineConfig } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';

process.env.MINGJING_Q9_RUN_ID ??= `bjt-${new Date(Date.now() + 28800000).toISOString().replace(/[^0-9T]/g, '')}-${randomUUID().slice(0, 8)}`;
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'q9-night-visual.spec.ts',
  globalSetup: fileURLToPath(new URL('./tests/e2e/q9-night-helpers.ts', import.meta.url)),
  timeout: 90000,
  fullyParallel: true,
  workers: 2,
  retries: 0,
  outputDir: `test-results/q9-night/${process.env.MINGJING_Q9_RUN_ID}`,
  reporter: [['list'], ['json', { outputFile: `test-results/q9-night/${process.env.MINGJING_Q9_RUN_ID}/report.json` }]],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    channel: process.env.CI ? undefined : 'chrome',
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    reducedMotion: 'reduce',
    deviceScaleFactor: 1,
    serviceWorkers: 'allow',
    trace: 'retain-on-failure',
  },
  webServer: { command: 'npm run preview', url: 'http://127.0.0.1:4173', reuseExistingServer: true },
});
