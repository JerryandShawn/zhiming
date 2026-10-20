import { test, expect, type Locator, type Page } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { auditNight, guardNight, assertNightQuiet } from './night-helpers';
async function tabTo(page: Page, target: Locator) {
  for (let index = 0; index < 180; index++) {
    if (await target.evaluate((element) => element === document.activeElement)) return;
    await page.keyboard.press('Tab');
  }
  await expect(target).toBeFocused();
}
async function activate(page: Page, target: Locator) {
  await tabTo(page, target);
  await page.keyboard.press('Enter');
}
async function capture(page: Page, name: string) {
  const folder = process.env.NIGHT_EVIDENCE_DIR ?? 'evidence/2026-10-21/tools-boundaries';
  await fs.mkdir(folder, { recursive: true });
  await fs.writeFile(
    path.join(folder, `${name}.png`),
    await page.screenshot({ fullPage: true, animations: 'disabled' }),
    { flag: 'wx' },
  );
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
for (const width of [390, 1440]) {
  test(`工具键盘：选择器、排序、依据回焦和双确认 ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/?tools=demo#/chart?tool=window_search');
    const range = page.getByRole('combobox', { name: '查看范围', exact: true });
    await expect(range).toBeVisible();
    await tabTo(page, range);
    await page.keyboard.press('ArrowDown');
    await expect(page.getByRole('listbox', { name: '查看范围', exact: true })).toBeVisible();
    await page.keyboard.press('End');
    await page.keyboard.press('Home');
    await page.keyboard.press('Enter');
    await expect(range).toBeFocused();
    await activate(page, page.getByRole('button', { name: '查看当前样例条件', exact: true }));
    const result = page.locator('[data-tool-document]');
    await expect(result).toBeVisible();
    await tabTo(page, result.getByRole('region', { name: '全区间日期排序', exact: true }));
    const first = result.locator('.tool-candidate').first();
    await activate(page, first.locator('summary').first());
    const evidence = first.getByRole('button', { name: /^依据〔/ }).first();
    await activate(page, evidence);
    const dialog = page.getByRole('dialog', { name: /^本结果依据〔/ });
    await expect(dialog).toBeVisible();
    for (let n = 0; n < 4; n++) {
      await page.keyboard.press('Tab');
      expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
    }
    await auditNight(page);
    await capture(page, `tools-keyboard-evidence-${width}`);
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(evidence).toBeFocused();
    await activate(page, page.getByRole('link', { name: '合盘', exact: true }));
    const a = page.getByRole('checkbox', { name: '允许本次展示A方合成盘面', exact: true });
    const b = page.getByRole('checkbox', { name: '允许本次展示B方合成盘面', exact: true });
    await tabTo(page, a);
    await page.keyboard.press('Space');
    await expect(page.getByRole('button', { name: '查看已确认的样例', exact: true })).toBeDisabled();
    await tabTo(page, b);
    await page.keyboard.press('Space');
    await activate(page, page.getByRole('button', { name: '查看已确认的样例', exact: true }));
    await expect(result).toBeVisible();
    await activate(page, page.getByRole('button', { name: '撤回本次展示', exact: true }));
    await expect(result).toHaveCount(0);
    await expect(a).not.toBeChecked();
    await expect(b).not.toBeChecked();
    await expect(page.getByRole('button', { name: '撤回本次展示', exact: true })).toBeFocused();
    await auditNight(page);
  });
}
test('公开目录校验失败可重试，失败期间不展示任何旧盘面', async ({ page }) => {
  let invalid = true;
  await page.route('**/data/tools/manifest.json', async (route) =>
    invalid
      ? route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ schema: 'wrong' }) })
      : route.continue(),
  );
  await page.goto('/?tools=demo#/chart?tool=synastry');
  await expect(page.getByRole('heading', { name: '这次样例没有展开', exact: true })).toBeVisible();
  await expect(page.locator('[data-tool-document]')).toHaveCount(0);
  await auditNight(page);
  await capture(page, 'tools-invalid-manifest');
  invalid = false;
  await page.getByRole('button', { name: '重新载入公开样例', exact: true }).click();
  await expect(page.getByRole('heading', { name: '合盘 · 先确认，再看结构', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '查看已确认的样例', exact: true })).toBeDisabled();
  await expect(page.locator('[data-tool-document]')).toHaveCount(0);
  await auditNight(page);
  await capture(page, 'tools-retry-fresh-confirmation');
});
