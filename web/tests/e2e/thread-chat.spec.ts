import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import { cinnabarUsages } from './appearance';

const runId = process.env.MINGJING_THREAD_CHAT_RUN_ID ?? new Date().toISOString();
const batch = runId.replace(/[^a-zA-Z0-9-]/g, '-');
const evidence = path.resolve('evidence/2026-10-30/thread-chat');
const auditsDirectory = path.resolve('test-results/thread-chat-evidence', batch, 'audits');
const acceptance = {
  run_id: 'synthetic:run1',
  thread_id: 'life:self',
  status: 'queued',
  runtime: 'v4',
  run_url: '/api/runs/synthetic:run1',
  events_url: '/api/runs/synthetic:run1/events',
};
const envelope = {
  schema: 'core4.0',
  message_id: 'synthetic:message1',
  text: '这是经本轮状态核对后显示的合成回答。',
  receipts: [],
  used_fact_ids: [],
  used_claim_ids: [],
  asked: null,
  options: null,
  review: { state: 'passed', reasons: [] },
  usage: {},
};
const frame = (seq: number, type: string, body: Record<string, unknown>) =>
  `id: ${seq}\nevent: ${type}\ndata: ${JSON.stringify({ v: 1, run_id: acceptance.run_id, seq, ts: '2026-10-30T18:00:00+08:00', ...body })}\n\n`;

async function mockThread(page: Page, stop = false) {
  let persisted = 'running';
  await page.route('**/api/history?*', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/threads/life%3Aself/messages', (route) => route.fulfill({ status: 202, json: acceptance }));
  await page.route('**/api/runs/synthetic:run1/events', async (route) => {
    if (!stop) persisted = 'succeeded';
    await route.fulfill({
      contentType: 'text/event-stream; charset=utf-8',
      body: stop
        ? frame(1, 'text_delta', { text: '合成部分回答' })
        : frame(1, 'text_delta', { text: '合成流式草稿' }) +
          frame(2, 'final', { message_id: envelope.message_id, envelope }),
    });
  });
  await page.route('**/api/runs/synthetic:run1/cancel', async (route) => {
    persisted = 'cancelled';
    await route.fulfill({ json: { ok: true, run_id: acceptance.run_id } });
  });
  await page.route('**/api/runs/synthetic:run1', (route) =>
    route.fulfill({
      json: {
        id: acceptance.run_id,
        operation_id: 'synthetic:operation1',
        status: persisted,
        calls: 0,
        call_limit: 12,
        attempts: 1,
        checkpoint: {},
        dependencies: [],
        error: null,
        result: persisted === 'succeeded' ? { ...envelope, answer: envelope.text } : {},
      },
    }),
  );
}

async function open(page: Page, theme = 'light') {
  await page.addInitScript((value) => {
    sessionStorage.setItem('mingjing-auth-token', 'synthetic-browser');
    localStorage.setItem('mingjing-theme', value);
  }, theme);
  await page.goto('/#/chat');
  await expect(page.locator('[data-page="chat"][data-runtime="thread-v4"]')).toBeVisible();
}

test.beforeAll(async () => {
  await fs.mkdir(path.join(evidence, 'screenshots'), { recursive: true });
  await fs.mkdir(auditsDirectory, { recursive: true });
});

test.afterAll(async () => {
  type Audit = {
    run_id: string;
    theme: string;
    viewport: { width: number; height: number };
    overflow: boolean;
    small_text: string[];
    cinnabar_uses: unknown[];
    outside_requests: string[];
    page_errors: string[];
    console_messages: string[];
    violations: unknown[];
  };
  const files = await fs.readdir(auditsDirectory);
  const audits = (
    await Promise.all(
      files
        .filter((file) => file.endsWith('.json'))
        .map(async (file) => JSON.parse(await fs.readFile(path.join(auditsDirectory, file), 'utf8')) as Audit),
    )
  ).filter((item) => item.run_id === runId);
  const summary = {
    schema: 'frontend-thread-chat-visual-v1',
    run_id: runId,
    captured_at: new Date().toISOString(),
    node_version: process.version,
    expected_combinations: 8,
    captured_combinations: audits.length,
    mode: 'production default #/chat with synthetic v4 API; final authority-confirmed answer',
    checks: {
      overflowing_pages: audits.filter((item) => item.overflow).length,
      small_text_pages: audits.filter((item) => item.small_text.length).length,
      cinnabar_budget_failures: audits.filter((item) => item.cinnabar_uses.length > 3).length,
      external_requests: audits.reduce((sum, item) => sum + item.outside_requests.length, 0),
      javascript_errors: audits.reduce((sum, item) => sum + item.page_errors.length, 0),
      console_messages: audits.reduce((sum, item) => sum + item.console_messages.length, 0),
      accessibility_violations: audits.reduce((sum, item) => sum + item.violations.length, 0),
    },
    captures: audits.map((item) => ({
      theme: item.theme,
      viewport: item.viewport,
      screenshot: `web/evidence/2026-10-30/thread-chat/screenshots/chat-${item.theme}-${item.viewport.width}.png`,
    })),
  };
  await fs.writeFile(path.join(evidence, 'visual-summary.json'), JSON.stringify(summary, null, 2) + '\n');
});

test('生产默认对话经 v4 提交、事件流和权威终稿后清空原 pending', async ({ page }) => {
  const calls: string[] = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/'))
      calls.push(`${request.method()} ${new URL(request.url()).pathname}`);
  });
  await mockThread(page);
  await open(page);
  await page.getByRole('textbox', { name: '和明镜说说' }).fill('浏览器合成问题');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.getByText(envelope.text, { exact: true })).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() =>
        Object.keys(sessionStorage)
          .filter((key) => key.startsWith('mingjing-chat-pending-v1:') && !key.endsWith(':draft'))
          .map((key) => sessionStorage.getItem(key)),
      ),
    )
    .toEqual([]);
  expect(calls).toEqual([
    'GET /api/history',
    'POST /api/threads/life%3Aself/messages',
    'GET /api/runs/synthetic:run1',
    'GET /api/runs/synthetic:run1/events',
    'GET /api/runs/synthetic:run1',
    'GET /api/history',
  ]);
});

test('停止只调用原运行取消并保留部分正文', async ({ page }) => {
  await mockThread(page, true);
  await open(page);
  await page.getByRole('textbox', { name: '和明镜说说' }).fill('浏览器停止问题');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.getByText('合成部分回答', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '停止回答', exact: true }).click();
  await expect(page.getByRole('status', { name: '停止反馈', exact: true })).toHaveText('本轮已停止，已出的内容保留。');
  await expect(page.getByText('合成部分回答', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '继续原来这一轮', exact: true })).toBeVisible();
});

for (const viewport of [
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
])
  for (const theme of ['light', 'dark'])
    test(`thread chat ${theme} ${viewport.width}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      const outside: string[] = [],
        errors: string[] = [],
        consoleMessages: string[] = [];
      page.on('request', (request) => {
        const url = new URL(request.url());
        if (['http:', 'https:'].includes(url.protocol) && url.origin !== 'http://127.0.0.1:4173')
          outside.push(url.origin);
      });
      page.on('pageerror', (error) => errors.push(error.message));
      page.on('console', (message) => {
        if (['warning', 'error'].includes(message.type())) consoleMessages.push(message.text());
      });
      await mockThread(page);
      await open(page, theme);
      await page.getByRole('textbox', { name: '和明镜说说' }).fill('浏览器合成问题');
      await page.getByRole('button', { name: '发送', exact: true }).click();
      await expect(page.getByText(envelope.text, { exact: true })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await page.waitForLoadState('networkidle');
      const visual = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth > innerWidth,
        small_text: Array.from(document.querySelectorAll('main *'))
          .filter(
            (element) =>
              element instanceof HTMLElement &&
              Array.from(element.childNodes).some((node) => node.nodeType === 3 && node.textContent?.trim()) &&
              element.getBoundingClientRect().width > 0 &&
              getComputedStyle(element).display !== 'none' &&
              parseFloat(getComputedStyle(element).fontSize) < 13 &&
              !element.closest('.citation'),
          )
          .map((element) => element.className),
      }));
      const cinnabar = await page.evaluate(cinnabarUsages);
      const axe = await new AxeBuilder({ page }).analyze();
      const filename = `chat-${theme}-${viewport.width}`;
      await page.screenshot({
        path: path.join(evidence, 'screenshots', `${filename}.png`),
        fullPage: true,
        animations: 'disabled',
      });
      await fs.writeFile(
        path.join(auditsDirectory, `${filename}.json`),
        JSON.stringify(
          {
            run_id: runId,
            theme,
            viewport,
            overflow: visual.overflow,
            small_text: visual.small_text,
            cinnabar_uses: cinnabar,
            outside_requests: outside,
            page_errors: errors,
            console_messages: consoleMessages,
            violations: axe.violations,
          },
          null,
          2,
        ) + '\n',
      );
      expect.soft(visual.overflow).toBe(false);
      expect.soft(visual.small_text).toEqual([]);
      expect.soft(cinnabar.length).toBeLessThanOrEqual(3);
      expect.soft(outside).toEqual([]);
      expect.soft(errors).toEqual([]);
      expect.soft(consoleMessages).toEqual([]);
      expect.soft(axe.violations).toEqual([]);
    });
