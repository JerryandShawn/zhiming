import { defineConfig } from '@playwright/test';
import { randomUUID } from 'node:crypto';
process.env.MINGJING_Q9_STATIC_INVOCATION ??= randomUUID();
process.env.MINGJING_Q9_RUN_ID ??= `q9-${new Date().toISOString().replace(/[^a-zA-Z0-9-]/g, '-')}`;
if (!/^[a-zA-Z0-9-]{1,90}$/.test(process.env.MINGJING_Q9_RUN_ID)) throw new Error('Invalid visual run id');
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'q9-static-visual.spec.ts',
  timeout: 60000,
  workers: 2,
  outputDir: `test-results/q9-static/${process.env.MINGJING_Q9_RUN_ID}`,
  reporter: [
    ['list'],
    ['json', { outputFile: `test-results/q9-static/${process.env.MINGJING_Q9_RUN_ID}/report.json` }],
  ],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    channel: process.env.CI ? undefined : 'chrome',
    headless: true,
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    reducedMotion: 'reduce',
    serviceWorkers: 'allow',
    trace: 'retain-on-failure',
  },
  webServer: { command: 'npm run preview', url: 'http://127.0.0.1:4173', reuseExistingServer: true },
});
