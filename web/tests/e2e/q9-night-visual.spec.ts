import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { captureQ9, guardQ9, q9Origin } from './q9-night-helpers';

const viewports = [
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
];
const states = [
  ...['today', 'chat', 'chart', 'tarot', 'cases', 'me', 'settings'].map((name) => ({
    id: `night-${name}`,
    name,
    url: `/?night=demo#/${name}`,
  })),
  { id: 'spaces-chat', name: 'chat', url: '/?spaces=demo#/chat?space=career&topic=interview' },
  { id: 'spaces-me', name: 'me', url: '/?spaces=demo#/me' },
  { id: 'spaces-organize', name: 'organize', url: '/?spaces=demo#/organize' },
  { id: 'guide', name: 'chat', url: '/?night=demo#/chat' },
  { id: 'organize-review', name: 'organize-review', url: '/?spaces=demo#/organize-review' },
  { id: 'recovery', name: 'recovery', url: '/?night=demo#/recovery' },
];
async function prepare(page: Page, item: (typeof states)[number]) {
  await page.goto(item.url, { waitUntil: 'domcontentloaded' });
  if (item.id === 'organize-review') {
    const review = page.locator('[data-runtime="organize-v2"]');
    await expect(review).toHaveAttribute('data-state', 'draft');
    await expect(review.locator('[data-space-id]')).toHaveCount(7);
    await expect(review.locator('[data-topic-id]')).toHaveCount(8);
    await expect(review.locator('[data-segment-id]')).toHaveCount(8);
    await expect(page.getByRole('region', { name: '不确定，待你整理', exact: true })).toBeVisible();
  } else if (item.id === 'recovery') {
    const recovery = page.locator('[data-runtime="night-recovery"]');
    await expect(recovery).toHaveAttribute('data-transport', 'memory');
    await expect(recovery).toHaveAttribute('data-complete', 'true');
    await expect(recovery).toHaveAttribute('data-connection', 'closed');
    await expect(recovery).toContainText('恢复后的正文已经替换重复片段。接着从这里继续。');
    await expect(recovery).not.toContainText('恢复前的重复旧片段。');
  } else {
    await expect(page.locator(`[data-page="${item.name}"]`)).toBeVisible();
    if (item.id === 'night-chat' || item.id === 'guide')
      await expect(page.locator('[data-complete="true"]')).toBeVisible();
    if (item.id === 'night-today') await todayReady(page);
    if (item.id === 'night-chart') await expect(page.locator('[data-runtime="night-chart-samples"]')).toBeVisible();
    if (item.id === 'night-me') await expect(page.locator('[data-runtime="night-me"]')).toBeVisible();
    if (item.id === 'night-settings') await expect(page.locator('[data-runtime="night-settings"]')).toBeVisible();
    if (item.id === 'spaces-chat') await expect(page.locator('[data-message]')).toHaveCount(4);
    if (item.id === 'guide') {
      await page.getByRole('button', { name: '初次相识演示', exact: true }).click();
      await page.getByRole('button', { name: '开始认识', exact: true }).click();
      await expect(page.locator('[data-runtime="night-onboarding"]')).toHaveAttribute('data-step', 'user_name');
    }
  }
  await page.evaluate(() => document.fonts.ready);
}
async function todayReady(page: Page) {
  const today = page.locator('[data-runtime="night-today"]');
  await expect(today).toHaveAttribute('data-load-state', 'ready');
  await expect(today).toHaveAttribute('data-today', '2026-10-21');
  await expect(today.getByRole('heading', { name: /10月21日.*星期三/ })).toBeVisible();
  await expect(today.locator('[data-daily-system]')).toHaveCount(3);
  await expect(today.getByRole('list', { name: '安排与提醒列表', exact: true }).getByRole('listitem')).toHaveCount(3);
  await expect(today.locator('.button.primary')).toHaveCount(1);
  await expect(today).toContainText('节假日、调休、农历及节气资料尚未载入');
}
test.beforeEach(async ({ page }) => {
  // Fixed Date preserves the sample day while browser timers and animations keep advancing.
  await page.clock.setFixedTime(new Date('2026-10-21T07:15:00+08:00'));
});

for (const viewport of viewports)
  for (const theme of ['light', 'dark'])
    for (const item of states) {
      test(`${item.id} ${theme} ${viewport.width}`, async ({ page, context }) => {
        await page.setViewportSize(viewport);
        await page.addInitScript((theme) => localStorage.setItem('mingjing-theme', theme), theme);
        const activity = await guardQ9(context, page);
        let readinessError = '';
        try {
          await prepare(page, item);
        } catch (error) {
          readinessError = error instanceof Error ? error.message : 'readiness failed';
        }
        await captureQ9(
          page,
          `${item.id}-${theme}-${viewport.width}`,
          {
            state: item.id,
            route: item.url,
            viewport,
            theme,
            mode: item.id === 'recovery' ? 'memory-recovery' : 'synthetic-page',
          },
          activity,
          readinessError,
        );
      });
    }

type ShellManifest = { version: string; assets: { path: string; bytes: number; sha256: string }[] };
async function cacheProof(page: Page, manifest: ShellManifest) {
  const proof = await page.evaluate(async (manifest) => {
    const registration = await navigator.serviceWorker.ready;
    const expectedCache = `mingjing-shell-v1:${encodeURIComponent(new URL(registration.scope).pathname)}:${manifest.version}`;
    const names = await caches.keys(),
      rows = [];
    for (const name of names) {
      const cache = await caches.open(name);
      for (const request of await cache.keys()) {
        const response = await cache.match(request),
          bytes = await response!.arrayBuffer();
        rows.push({
          cache: name,
          path: new URL(request.url).pathname.slice(1),
          bytes: bytes.byteLength,
          sha256: [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
            .map((value) => value.toString(16).padStart(2, '0'))
            .join(''),
        });
      }
    }
    return { names, expectedCache, rows };
  }, manifest);
  expect(proof.names).toEqual([proof.expectedCache]);
  expect(proof.rows.map((row) => row.path).sort()).toEqual(manifest.assets.map((item) => item.path).sort());
  for (const asset of manifest.assets)
    expect(proof.rows.find((row) => row.path === asset.path)).toEqual({ cache: proof.expectedCache, ...asset });
  expect(proof.rows.every((row) => !/^\/?(?:api|static|__test__|__frontend_fixture__)(?:\/|$)/.test(row.path))).toBe(
    true,
  );
  return proof;
}
async function offlineReady(page: Page, context: BrowserContext) {
  await prepare(page, states[0]);
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });
  expect(await page.evaluate(() => navigator.serviceWorker.controller)).toBeNull();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true);
  await todayReady(page);
  await page.evaluate(() => document.fonts.ready);
  const manifest = await page.evaluate(async () => {
    const response = await fetch('/pwa/shell-manifest.json', { credentials: 'omit', cache: 'no-store' });
    if (!response.ok) throw new Error('Missing built shell manifest');
    return (await response.json()) as ShellManifest;
  });
  const before = await cacheProof(page, manifest);
  await context.setOffline(true);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('status').filter({ hasText: '离线中' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-network', 'offline');
  await todayReady(page);
  await page.evaluate(() => document.fonts.ready);
  expect(
    await page.locator('html').evaluate((node) => getComputedStyle(node).getPropertyValue('--font-sans')),
  ).not.toMatch(/Noto|Source Han/);
  const after = await cacheProof(page, manifest);
  expect(after).toEqual(before);
  return { shell_version: manifest.version, before, after, dynamic_data_cached: false, online_origin: q9Origin };
}
for (const viewport of viewports)
  for (const theme of ['light', 'dark']) {
    test(`offline-today ${theme} ${viewport.width}`, async ({ page, context }) => {
      await page.setViewportSize(viewport);
      await page.addInitScript((theme) => localStorage.setItem('mingjing-theme', theme), theme);
      const activity = await guardQ9(context, page);
      let readinessError = '',
        cache;
      try {
        cache = await offlineReady(page, context);
      } catch (error) {
        readinessError = error instanceof Error ? error.message : 'offline readiness failed';
      }
      try {
        await captureQ9(
          page,
          `offline-today-${theme}-${viewport.width}`,
          {
            state: 'offline-today',
            route: '/?night=demo#/today',
            viewport,
            theme,
            mode: 'real-service-worker-offline-shell',
            cache,
          },
          activity,
          readinessError,
        );
      } finally {
        await context.setOffline(false);
      }
    });
  }
