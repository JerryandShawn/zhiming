import { test, expect, type Locator, type Page } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { auditNight, guardNight, assertNightQuiet } from './night-helpers';

async function capture(page: Page, name: string) {
  await page.evaluate(() => window.scrollTo(0, 0));
  const folder = process.env.NIGHT_EVIDENCE_DIR ?? 'evidence/2026-10-21/tools-form-fields';
  await fs.mkdir(folder, { recursive: true });
  await fs.writeFile(
    path.join(folder, `${name}.png`),
    await page.screenshot({ fullPage: true, animations: 'disabled' }),
    { flag: 'wx' },
  );
}
async function expectLinkedError(field: Locator, message: RegExp) {
  await expect(field).toHaveAttribute('aria-invalid', 'true');
  const ids = ((await field.getAttribute('aria-describedby')) ?? '').trim().split(/\s+/).filter(Boolean);
  expect(ids.length).toBeGreaterThan(0);
  const text = await field.evaluate(
    (_element, linked) => linked.map((id) => document.getElementById(id)?.textContent ?? '').join(' '),
    ids,
  );
  expect(text).toMatch(message);
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
  test(`择日字段校验、焦点与修正草稿 ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(
      (theme) => localStorage.setItem('mingjing-theme', theme),
      width === 390 ? 'dark' : 'light',
    );
    await page.goto('/?tools=demo#/chart?tool=window_search');
    const start = page.getByLabel('起始日期（北京时间）', { exact: true }),
      end = page.getByLabel('结束日期（含当日）', { exact: true });
    await start.fill('');
    await end.fill('');
    await page.getByRole('button', { name: '查看当前样例条件', exact: true }).click();
    await expect(start).toBeFocused();
    await expectLinkedError(start, /请填写日期/);
    await expectLinkedError(end, /请填写日期/);
    await page.getByRole('link', { name: '结束日期：请填写日期。', exact: true }).click();
    await expect(end).toBeFocused();
    await page.getByRole('link', { name: '起始日期：请填写日期。', exact: true }).click();
    await expect(start).toBeFocused();
    await expect(page.locator('[data-tool-document]')).toHaveCount(0);
    await auditNight(page);
    await capture(page, `window-fields-invalid-${width}`);
    await start.fill('2026-10-21');
    await end.fill('2026-10-27');
    await page.getByRole('button', { name: '查看当前样例条件', exact: true }).click();
    await expect(page.getByRole('heading', { name: '整个区间的项目排序', exact: true })).toBeVisible();
    await expect(start).toHaveValue('2026-10-21');
    await expect(end).toHaveValue('2026-10-27');
    await expect(page.locator('[aria-invalid="true"]')).toHaveCount(0);
    await auditNight(page);
    await capture(page, `window-fields-corrected-${width}`);
  });

  test(`合盘查询校验与样例不可用保持分开 ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(
      (theme) => localStorage.setItem('mingjing-theme', theme),
      width === 390 ? 'dark' : 'light',
    );
    await page.goto('/?tools=demo#/chart?tool=synastry');
    const date = page.getByLabel('核对日期（北京时间）', { exact: true }),
      orb = page.getByRole('textbox', { name: '统一相位容许度（度）', exact: true }),
      read = page.getByRole('button', { name: '查看已确认的样例', exact: true });
    await date.fill('');
    await orb.fill('六');
    await expect(read).toBeDisabled();
    await page.getByRole('button', { name: '核对查询条件', exact: true }).click();
    await expect(date).toBeFocused();
    await expectLinkedError(date, /请填写日期/);
    await expectLinkedError(orb, /0至10度/);
    await expect(orb).toHaveValue('六');
    await expect(page.locator('[data-tool-document]')).toHaveCount(0);
    await auditNight(page);
    await capture(page, `synastry-fields-invalid-${width}`);
    await date.fill('2026-10-21');
    await orb.fill('0');
    await page.getByRole('button', { name: '核对查询条件', exact: true }).click();
    await expect(
      page.getByRole('region', { name: '本次查询条件', exact: true }).getByText('0°', { exact: true }),
    ).toBeVisible();
    await expect(read).toBeDisabled();
    await page.getByRole('checkbox', { name: '允许本次展示A方合成盘面', exact: true }).check();
    await page.getByRole('checkbox', { name: '允许本次展示B方合成盘面', exact: true }).check();
    await read.click();
    await expect(page.locator('[data-published-state="unavailable"]')).toBeVisible();
    await expect(page.locator('[aria-invalid="true"]')).toHaveCount(0);
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(orb).toHaveValue('0');
    await expect(page.locator('[data-tool-document]')).toHaveCount(0);
    await auditNight(page);
    await capture(page, `synastry-valid-unavailable-${width}`);
  });
}
