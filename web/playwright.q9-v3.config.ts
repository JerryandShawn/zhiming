import { randomUUID } from 'node:crypto';
import { defineConfig } from '@playwright/test';

process.env.Q9_V3_RUN_ID ??= `${new Date().toISOString()}-${randomUUID().slice(0, 8)}`;
const batch = process.env.Q9_V3_RUN_ID.replace(/[^a-zA-Z0-9-]/g, '-');

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'q9-v3-visual.spec.ts',
  timeout: 120000,
  expect: { timeout: 15000 },
  workers: 2,
  fullyParallel: true,
  retries: 0,
  outputDir: `test-results/q9-v3/${batch}`,
  reporter: [['list'], ['json', { outputFile: `evidence/2026-10-21/Q9/v3/${batch}/playwright.json` }]],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    channel: process.env.CI ? undefined : 'chrome',
    headless: true,
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    reducedMotion: 'reduce',
    deviceScaleFactor: 1,
    serviceWorkers: 'allow',
    // The profile is synthetic, but keep request payloads and form values out of diagnostics.
    trace: 'off',
    video: 'off',
    screenshot: 'off',
  },
});
