import { test, expect, type Page, type TestInfo } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { auditNight } from './night-helpers';

const marker = 'SYNTHETIC_CHUNK_FAILURE';
async function failChunk(page: Page, entry: string) {
  const manifest = JSON.parse(await fs.readFile('../static/dist/.vite/manifest.json', 'utf8')) as Record<
    string,
    { file: string; name?: string; isDynamicEntry?: boolean }
  >;
  const name = entry
    .split('/')
    .at(-1)!
    .replace(/\.tsx$/, '');
  const candidates = manifest[entry]
    ? [manifest[entry]]
    : Object.values(manifest).filter((row) => row.name === name && row.isDynamicEntry);
  expect(candidates).toHaveLength(1);
  const file = candidates[0].file;
  let enabled = true,
    failed = 0;
  await page.route(`**/${file}`, async (route) => {
    if (enabled) {
      failed++;
      await route.fulfill({ status: 200, contentType: 'application/javascript', body: `throw new Error("${marker}")` });
    } else await route.continue();
  });
  return {
    restore: () => {
      enabled = false;
    },
    count: () => failed,
  };
}
async function capture(page: Page, name: string, info: TestInfo) {
  await page.evaluate(() => window.scrollTo(0, 0));
  const folder = process.env.NIGHT_EVIDENCE_DIR ?? 'evidence/2026-10-21/route-recovery';
  await fs.mkdir(folder, { recursive: true });
  const file = path.join(folder, `${name}.png`);
  await fs.writeFile(file, await page.screenshot({ fullPage: true, animations: 'disabled' }), { flag: 'wx' });
  info.annotations.push({ type: 'route_recovery_screenshot', description: file.replaceAll('\\', '/') });
}
async function guard(page: Page) {
  const calls: string[] = [],
    errors: string[] = [],
    logs: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => logs.push(m.text()));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (
      ['http:', 'https:'].includes(url.protocol) &&
      (url.origin !== 'http://127.0.0.1:4173' || /^\/api(?:\/|$)/.test(url.pathname))
    ) {
      calls.push(url.origin + url.pathname);
      await route.abort();
    } else await route.continue();
  });
  return () => {
    expect(calls).toEqual([]);
    expect(errors.every((e) => e.includes(marker))).toBe(true);
    expect(logs.every((e) => e.includes(marker))).toBe(true);
  };
}

test('普通分包失败保留导航，真实重载后恢复该页', async ({ page }, info) => {
  const quiet = await guard(page),
    failure = await failChunk(page, 'src/pages/Chart.tsx');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?preview=1#/chart');
  const recovery = page.locator('[data-route-recovery]');
  await expect(recovery).toBeVisible();
  expect(failure.count()).toBeGreaterThan(0);
  await expect(recovery.getByRole('heading', { name: '这页暂时没有展开' })).toBeFocused();
  await expect(page.locator('.tabbar')).toBeVisible();
  await expect(recovery).not.toContainText(marker);
  await auditNight(page);
  await capture(page, 'route-static-failed-390', info);
  failure.restore();
  await Promise.all([
    page.waitForEvent('load'),
    recovery.getByRole('button', { name: '重新载入页面', exact: true }).click(),
  ]);
  await expect(page.locator('[data-page="chart"]')).toBeVisible();
  await expect(recovery).toHaveCount(0);
  await auditNight(page);
  await capture(page, 'route-static-reloaded-390', info);
  quiet();
});

test('夜间子页失败后返回对话保留普通草稿和控制器', async ({ page }, info) => {
  const quiet = await guard(page),
    failure = await failChunk(page, 'src/night/charts/SampleChartPage.tsx');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.clock.setFixedTime(new Date('2026-10-21T08:00:00+08:00'));
  await page.goto('/?night=demo#/chat');
  const input = page.getByRole('textbox', { name: '和明镜说说', exact: true });
  await expect(input).toBeVisible();
  await input.fill('边界失败后仍保留的合成普通草稿');
  await page.locator('.rail').getByRole('link', { name: '命盘', exact: true }).click();
  const recovery = page.locator('[data-route-recovery]');
  await expect(recovery).toBeVisible();
  expect(failure.count()).toBeGreaterThan(0);
  await expect(recovery).toContainText('返回其他页面不会清除普通草稿');
  await auditNight(page);
  await capture(page, 'route-night-child-failed-1440', info);
  await recovery.getByRole('link', { name: '回到今日', exact: true }).click();
  await expect(page.locator('[data-runtime="night-today"]')).toHaveAttribute('data-load-state', 'ready');
  await page.locator('.rail').getByRole('link', { name: '对话', exact: true }).click();
  await expect(input).toHaveValue('边界失败后仍保留的合成普通草稿');
  await expect(recovery).toHaveCount(0);
  await auditNight(page);
  await capture(page, 'route-night-draft-preserved-1440', info);
  quiet();
});

test('夜间入口分包失败仍可到独立今日预览', async ({ page }, info) => {
  const quiet = await guard(page),
    failure = await failChunk(page, 'src/night/NightApp.tsx');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?night=demo#/chat');
  const recovery = page.locator('[data-route-recovery]');
  await expect(recovery).toBeVisible();
  expect(failure.count()).toBeGreaterThan(0);
  await expect(recovery).toContainText('回到今日将打开独立预览');
  await expect(page.locator('.tabbar')).toBeVisible();
  await auditNight(page);
  await capture(page, 'route-night-entry-failed-390', info);
  await recovery.getByRole('link', { name: '回到今日', exact: true }).click();
  await expect(page).toHaveURL(/\?preview=1#\/today$/);
  await expect(page.locator('[data-page="today"]')).toBeVisible();
  await expect(recovery).toHaveCount(0);
  await auditNight(page);
  await capture(page, 'route-night-entry-home-390', info);
  quiet();
});

test('默认今日分包失败时回到今日会真正重载', async ({ page }, info) => {
  const quiet = await guard(page),
    failure = await failChunk(page, 'src/pages/Today.tsx');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/?preview=1');
  const recovery = page.locator('[data-route-recovery]');
  await expect(recovery).toBeVisible();
  expect(failure.count()).toBeGreaterThan(0);
  await auditNight(page);
  await capture(page, 'route-default-home-failed-1440', info);
  failure.restore();
  await Promise.all([page.waitForEvent('load'), recovery.getByRole('link', { name: '回到今日', exact: true }).click()]);
  await expect(page.locator('[data-page="today"]')).toBeVisible();
  await expect(recovery).toHaveCount(0);
  quiet();
  await capture(page, 'route-default-home-reloaded-1440', info);
});
