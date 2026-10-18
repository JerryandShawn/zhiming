import { defineConfig } from '@playwright/test';

const port = Number(process.env.FRONTEND_TEST_PORT ?? 4173);
if (![4173, 4174].includes(port)) throw new Error('Frontend contracts require a local test port');
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'contracts.spec.ts',
  timeout: 60000,
  workers: 1,
  fullyParallel: false,
  outputDir: 'test-results/contracts',
  reporter: [['list'], ['json', { outputFile: 'test-results/frontend/contracts.json' }]],
  use: {
    baseURL,
    channel: process.env.CI ? undefined : 'chrome',
    headless: true,
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    reducedMotion: 'reduce',
    trace: 'retain-on-failure',
  },
  webServer: { command: `npm run dev -- --port ${port}`, url: baseURL, reuseExistingServer: true },
});
