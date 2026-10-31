import { test, expect, type Page } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { auditNight, guardNight, assertNightQuiet } from './night-helpers';

async function capture(page: Page, name: string) {
  const folder = process.env.NIGHT_EVIDENCE_DIR ?? 'evidence/2026-10-21/tools-pagination';
  await fs.mkdir(folder, { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.evaluate(() => document.fonts.ready);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await fs.writeFile(
    path.join(folder, `${name}.png`),
    await page.screenshot({ fullPage: true, animations: 'disabled' }),
    { flag: 'wx' },
  );
}
async function preset(page: Page, name: string) {
  await page.getByRole('combobox', { name: '查看范围', exact: true }).click();
  await page.getByRole('option', { name, exact: true }).click();
}
async function read(page: Page) {
  await page.getByRole('button', { name: '查看当前样例条件', exact: true }).click();
}
test.beforeEach(async ({ page }) => {
  guardNight(page);
  await page.clock.setFixedTime(new Date('2026-10-21T08:00:00+08:00'));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (
      ['http:', 'https:'].includes(url.protocol) &&
      (url.origin !== 'http://127.0.0.1:4173' || /^\/(?:api|__test__|__frontend_fixture__)(?:\/|$)/.test(url.pathname))
    )
      await route.abort();
    else await route.continue();
  });
  // Normal production shell worker registration remains enabled. This suite
  // neither blocks service workers nor clears caches to hide lifecycle issues.
});
test.afterEach(({ page }) => assertNightQuiet(page));

for (const width of [390, 1440]) {
  test(`分页按next_offset请求而不偷跳公开预设 ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(
      (theme) => localStorage.setItem('mingjing-theme', theme),
      width === 390 ? 'dark' : 'light',
    );
    await page.goto('/?tools=demo#/chart?tool=window_search');
    await preset(page, '第 4–6 名');
    await read(page);
    const result = page.locator('[data-tool-document]'),
      nav = page.getByRole('navigation', { name: '择日分页', exact: true }),
      next = nav.getByRole('button', { name: '下一页', exact: true });
    await expect(result).toBeVisible();
    await expect(nav).toContainText('当前返回3条');
    await expect(nav).toContainText('第4–6名');
    await auditNight(page);
    await capture(page, `pagination-middle-${width}`);
    await next.focus();
    await page.keyboard.press('Space');
    await expect(page.locator('[data-published-state="unavailable"]')).toBeVisible();
    await expect(nav).toContainText('偏移6');
    await expect(nav).toContainText('每页最多3天');
    await expect(result).toHaveCount(0);
    await expect(next).toBeFocused();
    await expect(next).toHaveAttribute('aria-disabled', 'true');
    await expect(page.locator('[aria-invalid="true"]')).toHaveCount(0);
    await auditNight(page);
    await capture(page, `pagination-next6-unavailable-${width}`);
    await preset(page, '末尾空页');
    await read(page);
    await expect(page.getByText('这已是末尾空页。', { exact: true })).toBeVisible();
    await expect(next).toHaveAttribute('aria-disabled', 'true');
    const previous = nav.getByRole('button', { name: '上一页', exact: true });
    await previous.focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('[data-published-state="unavailable"]')).toBeVisible();
    await expect(nav).toContainText('偏移4');
    await expect(previous).toBeFocused();
    await expect(result).toHaveCount(0);
    await auditNight(page);
    await capture(page, `pagination-empty-prev4-${width}`);
  });

  test(`上一页0比3与空白页大小不复用旧结果 ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(
      (theme) => localStorage.setItem('mingjing-theme', theme),
      width === 390 ? 'dark' : 'light',
    );
    await page.goto('/?tools=demo#/chart?tool=window_search');
    await preset(page, '第 4–6 名');
    await read(page);
    const nav = page.getByRole('navigation', { name: '择日分页', exact: true }),
      previous = nav.getByRole('button', { name: '上一页', exact: true }),
      size = page.getByRole('textbox', { name: '每页天数', exact: true });
    await expect(page.locator('[data-tool-document]')).toBeVisible();
    await previous.click();
    await expect(page.locator('[data-published-state="unavailable"]')).toBeVisible();
    await expect(nav).toContainText('偏移0');
    await expect(nav).toContainText('每页最多3天');
    await expect(previous).toHaveAttribute('aria-disabled', 'true');
    await expect(previous).toBeFocused();
    await auditNight(page);
    await capture(page, `pagination-prev0-limit3-${width}`);
    await size.fill('');
    await page.getByRole('button', { name: '应用每页天数', exact: true }).click();
    await expect(size).toHaveValue('');
    await expect(size).toHaveAttribute('aria-invalid', 'true');
    await expect(size).toBeFocused();
    for (const name of ['首页', '上一页', '下一页'])
      await expect(nav.getByRole('button', { name, exact: true })).toHaveAttribute('aria-disabled', 'true');
    await expect(page.locator('[data-tool-document]')).toHaveCount(0);
    await auditNight(page);
    await capture(page, `pagination-blank-limit-${width}`);
    await size.fill('31');
    await page.getByRole('button', { name: '应用每页天数', exact: true }).click();
    await expect(page.locator('[data-tool-document]')).toBeVisible();
    await expect(nav).toContainText('当前返回7条');
    await expect(size).toHaveValue('31');
    await expect(page.locator('[aria-invalid="true"]')).toHaveCount(0);
    await auditNight(page);
    await capture(page, `pagination-corrected-limit31-${width}`);
  });
}
