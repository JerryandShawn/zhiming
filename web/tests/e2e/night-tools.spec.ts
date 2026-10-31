import { test, expect, type Page, type TestInfo } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { auditNight, guardNight, assertNightQuiet } from './night-helpers';

const batch = (process.env.NIGHT_TOOLS_RUN_ID ?? new Date().toISOString()).replace(/[^a-zA-Z0-9-]/g, '-');
const directory = process.env.NIGHT_EVIDENCE_DIR ?? path.join('test-results/night-tools-evidence', batch);
async function capture(page: Page, name: string, info: TestInfo) {
  await fs.mkdir(directory, { recursive: true });
  const file = path.join(directory, `${name}.png`);
  await fs.writeFile(file, await page.screenshot({ fullPage: true, animations: 'disabled' }), { flag: 'wx' });
  info.annotations.push({ type: 'tool_screenshot', description: file.replaceAll('\\', '/') });
}
async function select(page: Page, name: string, value: string) {
  await page.getByRole('combobox', { name, exact: true }).click();
  await page.getByRole('option', { name: value, exact: true }).click();
}
async function settle(page: Page) {
  await page.evaluate(() => document.fonts.ready);
  await expect(page.locator('body')).not.toContainText('PRIVATE');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await auditNight(page);
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
});
test.afterEach(({ page }) => assertNightQuiet(page));

for (const width of [375, 390, 768, 1440])
  for (const theme of ['light', 'dark']) {
    test(`择日公开样例、分页、改条件清空与依据 ${width} ${theme}`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: width < 768 ? 844 : 900 });
      await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
      await page.goto('/?tools=demo#/chart?tool=window_search');
      await expect(page.getByRole('heading', { name: '择日 · 看一段时间的条件', exact: true })).toBeVisible();
      await expect(page.locator('[data-tool-document]')).toHaveCount(0);
      await page.getByRole('button', { name: '查看当前样例条件', exact: true }).click();
      const result = page.locator('[data-tool-document]');
      await expect(result.locator('.tool-candidate')).toHaveCount(7);
      await expect(result.locator('.tool-candidate').first()).toContainText('第 1 位 · 2026-10-25');
      await settle(page);
      await capture(page, `window-${width}-${theme}`, info);
      await result.locator('.tool-candidate').first().getByText('正向条件', { exact: false }).click();
      const evidence = result
        .locator('.tool-candidate')
        .first()
        .getByRole('button', { name: /^依据〔/ })
        .first();
      await evidence.click();
      const dialog = page.getByRole('dialog', { name: /^本结果依据〔/ });
      await expect(dialog).toBeVisible();
      await expect(dialog).toContainText('流派与方法：');
      await auditNight(page);
      await page.keyboard.press('Escape');
      await expect(dialog).toHaveCount(0);
      await expect(evidence).toBeFocused();
      await select(page, '查看范围', '第 4–6 名');
      await expect(result).toHaveCount(0);
      await page.getByRole('button', { name: '查看当前样例条件', exact: true }).click();
      await expect(result.locator('.tool-candidate')).toHaveCount(3);
      await expect(result.locator('.tool-candidate').first()).toContainText('第 4 位');
      await select(page, '查看范围', '末尾空页');
      await page.getByRole('button', { name: '查看当前样例条件', exact: true }).click();
      await expect(result.locator('.tool-candidate')).toHaveCount(0);
      await expect(result).toContainText('这已是末尾空页');
      await expect(result.locator('tbody tr')).toHaveCount(7);
      await select(page, '用途', '面试');
      await expect(result).toHaveCount(0);
      await page.getByRole('button', { name: '查看当前样例条件', exact: true }).click();
      await expect(page.getByRole('status').filter({ hasText: '没有' })).toBeVisible();
      await expect(result).toHaveCount(0);
      await settle(page);
    });

    test(`合盘本次双确认、两侧保留、撤回与换条件 ${width} ${theme}`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: width < 768 ? 844 : 900 });
      await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
      await page.goto('/?tools=demo#/chart?tool=synastry');
      await expect(page.getByRole('heading', { name: '合盘 · 先确认，再看结构', exact: true })).toBeVisible();
      const read = page.getByRole('button', { name: '查看已确认的样例', exact: true });
      const a = page.getByRole('checkbox', { name: '允许本次展示A方合成盘面', exact: true });
      const b = page.getByRole('checkbox', { name: '允许本次展示B方合成盘面', exact: true });
      await expect(read).toBeDisabled();
      await a.check();
      await expect(read).toBeDisabled();
      await b.check();
      await expect(read).toBeEnabled();
      await read.click();
      const result = page.locator('[data-tool-document]');
      await expect(result).toBeVisible();
      await expect(result.getByRole('region', { name: 'A方星体位置', exact: true }).locator('tbody tr')).toHaveCount(
        10,
      );
      await expect(result.getByRole('region', { name: 'B方星体位置', exact: true }).locator('tbody tr')).toHaveCount(
        10,
      );
      await expect(result).toContainText('不提供匹配总分');
      await settle(page);
      await capture(page, `synastry-${width}-${theme}`, info);
      await result.getByText('本结果的公开依据', { exact: true }).click();
      await result
        .getByRole('button', { name: /^依据〔/ })
        .first()
        .click();
      const dialog = page.getByRole('dialog', { name: /^本结果依据〔/ });
      await expect(dialog).toBeVisible();
      await page.keyboard.press('Tab');
      expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
      await page.keyboard.press('Escape');
      await page.getByRole('button', { name: '撤回本次展示', exact: true }).click();
      await expect(result).toHaveCount(0);
      await expect(a).not.toBeChecked();
      await expect(b).not.toBeChecked();
      await a.check();
      await b.check();
      await read.click();
      await expect(result).toBeVisible();
      await select(page, '本次比较用途', '朋友相处');
      await expect(result).toHaveCount(0);
      await expect(a).not.toBeChecked();
      await expect(b).not.toBeChecked();
      await expect(read).toBeDisabled();
      await a.check();
      await b.check();
      await read.click();
      await expect(page.getByRole('status').filter({ hasText: '没有' })).toBeVisible();
      await expect(result).toHaveCount(0);
      await settle(page);
    });
  }
