import { defineConfig } from '@playwright/test';

process.env.MINGJING_SPACES_VISUAL_RUN_ID ??= new Date().toISOString();
const batch = process.env.MINGJING_SPACES_VISUAL_RUN_ID.replace(/[^a-zA-Z0-9-]/g, '-');

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'spaces-visual.spec.ts',
  timeout: 60000,
  workers: 1,
  fullyParallel: false,
  outputDir: 'test-results/spaces-visual-runs',
  reporter: [['list'], ['json', { outputFile: `test-results/spaces-visual-evidence/${batch}/playwright.json` }]],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    channel: process.env.CI ? undefined : 'chrome',
    headless: true,
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    reducedMotion: 'reduce',
    trace: 'retain-on-failure',
  },
});
