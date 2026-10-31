import { expect, test, type Page } from '@playwright/test';
import { auditNight, captureNight } from './night-helpers';

test.use({ timezoneId: 'Asia/Shanghai', serviceWorkers: 'allow' });
const origin = 'http://127.0.0.1:4173';
const path = '/__frontend_fixture__/events-v1/synthetic-recovery/events';
const oldText = '恢复前的重复旧片段。';
const resetText = '恢复后的正文已经替换重复片段。';
const finalText = resetText + '接着从这里继续。';
type Activity = {
  api: string[];
  external: string[];
  errors: string[];
  console: string[];
  expectedErrors: number;
  requestFailures: number;
};
const activities = new WeakMap<Page, Activity>();
const root = (page: Page) => page.locator('[data-runtime="night-recovery"]');
function frame(seq: number, type: string, body: Record<string, unknown>) {
  return `id: ${seq}\r\nevent: ${type}\r\ndata: ${JSON.stringify({ v: 1, run_id: 'synthetic-recovery', seq, ts: '2026-10-21T01:30:00+08:00', ...body })}\r\n\r\n`;
}
const memory = {
  fact_id: 'synthetic-recovery-memory',
  write_status: 'undone',
  summary: '合成偏好已撤销',
  sensitive: false,
};
const initialBody = () =>
  frame(1, 'started', {
    thread_id: 'synthetic-recovery-thread',
    message_id: 'synthetic-recovery-message',
    incognito: false,
  }) +
  frame(2, 'text_delta', { text: oldText }) +
  frame(3, 'memory_receipt', memory) +
  frame(4, 'text_reset', { text: '残帧不能进入正文', reason: 'resumed', revision_id: 'synthetic-partial' }).slice(
    0,
    -2,
  );
const resumedBody = () =>
  frame(3, 'memory_receipt', memory) +
  frame(4, 'text_reset', { text: resetText, reason: 'resumed', revision_id: 'synthetic-resumed-1' }) +
  frame(5, 'text_delta', { text: '接着从这里继续。' }) +
  frame(6, 'final', {
    message_id: 'synthetic-recovery-message',
    envelope: {
      schema: 'core4.0',
      message_id: 'synthetic-recovery-message',
      text: finalText,
      receipts: [{ fact_id: 'synthetic-recovery-memory', write_status: 'undone' }],
      used_fact_ids: [],
      used_claim_ids: [],
      asked: null,
      options: null,
      review: { state: 'passed', reasons: [] },
      usage: { offline: true },
    },
  }) +
  frame(7, 'text_delta', { text: '终态后不能追加的污染' });
function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
}

test.beforeEach(async ({ page }) => {
  const activity: Activity = { api: [], external: [], errors: [], console: [], expectedErrors: 0, requestFailures: 0 };
  activities.set(page, activity);
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (/^\/api(?:\/|$)/.test(url.pathname) || /^\/__test__(?:\/|$)/.test(url.pathname))
      activity.api.push(url.pathname);
    if (['http:', 'https:'].includes(url.protocol) && url.origin !== origin) activity.external.push(url.origin);
  });
  page.on('pageerror', (error) => activity.errors.push(error.message));
  page.on('requestfailed', (request) => {
    if (request.url() === origin + path && request.failure()?.errorText === 'net::ERR_FAILED')
      ++activity.requestFailures;
  });
  page.on('console', (message) => {
    if (
      message.type() === 'error' &&
      message.location().url === origin + path &&
      message.text() === 'Failed to load resource: net::ERR_FAILED'
    ) {
      ++activity.expectedErrors;
    } else activity.console.push(`${message.type()}: ${message.text()}`);
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (
      (['http:', 'https:'].includes(url.protocol) && url.origin !== origin) ||
      /^\/(?:api|__test__)(?:\/|$)/.test(url.pathname)
    )
      await route.abort();
    else await route.continue();
  });
});
test.afterEach(({ page }) => {
  const activity = activities.get(page)!;
  expect({
    api: activity.api,
    external: activity.external,
    errors: activity.errors,
    console: activity.console,
  }).toEqual({ api: [], external: [], errors: [], console: [] });
  expect(activity.expectedErrors).toBeLessThanOrEqual(1);
  expect(activity.expectedErrors).toBe(activity.requestFailures);
});

async function fixture(page: Page, holdResume?: Promise<void>) {
  const requests: { cursor: string | null; headers: Record<string, string> }[] = [];
  const held = deferred();
  let failed = false;
  await page.route(origin + path, async (route) => {
    const request = route.request(),
      cursor = request.headers()['last-event-id'] ?? null;
    requests.push({ cursor, headers: request.headers() });
    if (!failed) {
      failed = true;
      await route.abort('failed');
      return;
    }
    if (cursor === '3' && holdResume) {
      held.resolve();
      await holdResume;
    }
    try {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: { 'Cache-Control': 'no-store' },
        body: cursor ? resumedBody() : initialBody(),
      });
    } catch (reason) {
      if (!page.isClosed() && request.failure()?.errorText !== 'net::ERR_ABORTED') throw reason;
    }
  });
  return { requests, held };
}
async function openRecovery(page: Page, width = 1440, theme = 'light', http = true) {
  await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
  await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
  await page.goto(`/?night=demo${http ? '&recoveryTransport=local-fixture' : ''}#/recovery`);
  await expect(root(page)).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}
async function completed(page: Page) {
  await expect(root(page)).toHaveAttribute('data-complete', 'true');
  await expect(root(page)).toHaveAttribute('data-last-event-id', '6');
  await expect(root(page).getByText(finalText, { exact: true })).toHaveCount(1);
  await expect(root(page)).not.toContainText(oldText);
  await expect(root(page)).not.toContainText('残帧不能进入正文');
  await expect(root(page)).not.toContainText('终态后不能追加的污染');
  await expect(root(page).getByText('已修订', { exact: true })).toHaveCount(0);
  await expect(root(page).getByRole('status').filter({ hasText: '已撤销，不会再提起' })).toHaveCount(1);
  await expect(root(page).getByRole('button', { name: /^(记住|撤销使用)$/ })).toHaveCount(0);
}

for (const theme of ['light', 'dark'])
  for (const width of [390, 1440]) {
    test(`本机HTTP断线补发、去重和权威替换 ${width} ${theme}`, async ({ page }) => {
      const transport = await fixture(page);
      await page.context().addCookies([{ url: origin, name: 'recovery-fixture-sentinel', value: 'synthetic' }]);
      await openRecovery(page, width, theme);
      await completed(page);
      expect(transport.requests.map(({ cursor }) => cursor)).toEqual([null, null, '3']);
      for (const request of transport.requests) {
        expect(request.headers.cookie).toBeUndefined();
        expect(request.headers['x-token']).toBeUndefined();
        expect(request.headers.authorization).toBeUndefined();
      }
      await expect(root(page)).toHaveAttribute('data-transport', 'local-fixture');
      await expect(root(page)).toContainText('不代表真实服务已经支持补发');
      await auditNight(page);
      await captureNight(page, `Q6-recovery-http-${width}-${theme}`, true);
    });
  }

test('停止挂起连接两秒内反馈，迟到HTTP结果不进入旧视图且可以重试', async ({ page }) => {
  const gate = deferred(),
    transport = await fixture(page, gate.promise);
  await openRecovery(page, 390, 'dark');
  await transport.held.promise;
  const startedAt = Date.now();
  await page.getByRole('button', { name: '停止恢复', exact: true }).click();
  await expect(root(page)).toHaveAttribute('data-connection', 'aborted', { timeout: 1500 });
  expect(Date.now() - startedAt).toBeLessThan(2000);
  gate.resolve();
  await expect(root(page)).toContainText(oldText);
  await expect(root(page)).not.toContainText(finalText);
  await auditNight(page);
  await captureNight(page, 'Q6-recovery-stopped-390-dark', true);
  await page.getByRole('button', { name: '重试连接', exact: true }).click();
  await completed(page);
  expect(transport.requests.some(({ cursor }) => cursor === '3')).toBe(true);
  await auditNight(page);
  await captureNight(page, 'Q6-recovery-retried-390-dark', true);
});

test('重放使用新一轮本地投影，不重复旧正文和记忆回执', async ({ page }) => {
  const transport = await fixture(page);
  await openRecovery(page);
  await completed(page);
  await page.getByRole('button', { name: '重放恢复演示', exact: true }).click();
  await expect.poll(() => transport.requests.length).toBe(5);
  await completed(page);
  expect(transport.requests.map(({ cursor }) => cursor)).toEqual([null, null, '3', null, '3']);
  await auditNight(page);
  await captureNight(page, 'Q6-recovery-replayed-1440-light', true);
});

test('往返恢复预览不会清空普通对话里尚未发送的草稿', async ({ page }) => {
  await fixture(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?night=demo&recoveryTransport=local-fixture#/chat');
  const ordinary = page.locator('[data-page="chat"][data-scenario="cards"]');
  await expect(ordinary).toHaveAttribute('data-complete', 'true');
  const draft = '普通对话未提交的合成草稿 Q6_RETAINED_DRAFT';
  await page.getByRole('textbox', { name: '和明镜说说', exact: true }).fill(draft);
  await page.evaluate(() => {
    location.hash = '/recovery';
  });
  await completed(page);
  await page.getByRole('link', { name: '回普通对话', exact: true }).click();
  await expect(page.getByRole('textbox', { name: '和明镜说说', exact: true })).toHaveValue(draft);
  await expect(root(page)).toHaveCount(0);
  await expect(ordinary).toHaveAttribute('data-complete', 'true');
  await auditNight(page);
  await captureNight(page, 'Q6-recovery-normal-draft-retained-390', true);
});

test('没有显式测试query时只运行内存恢复，不发专用HTTP请求', async ({ page }) => {
  const transport = await fixture(page);
  await openRecovery(page, 390, 'light', false);
  await completed(page);
  await expect(root(page)).toHaveAttribute('data-transport', 'memory');
  expect(transport.requests).toEqual([]);
  expect(activities.get(page)!.requestFailures).toBe(0);
  await auditNight(page);
  await captureNight(page, 'Q6-recovery-memory-390-light', true);
});
