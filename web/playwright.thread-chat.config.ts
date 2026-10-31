import { defineConfig } from '@playwright/test';

process.env.MINGJING_THREAD_CHAT_RUN_ID ??= new Date().toISOString();
const batch = process.env.MINGJING_THREAD_CHAT_RUN_ID.replace(/[^a-zA-Z0-9-]/g, '-');

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'thread-chat.spec.ts',
  timeout: 60000,
  workers: 1,
  outputDir: 'test-results/thread-chat-runs',
  reporter: [['list'], ['json', { outputFile: `test-results/thread-chat-evidence/${batch}/playwright.json` }]],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    channel: process.env.CI ? undefined : 'chrome',
    headless: true,
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    reducedMotion: 'reduce',
    trace: 'retain-on-failure',
  },
  webServer: { command: 'npm run preview', url: 'http://127.0.0.1:4173', reuseExistingServer: !process.env.CI },
});
