import { expect, test } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { auditNight, assertNightQuiet, guardNight, openNight } from './night-helpers';

test.beforeEach(({ page }) => guardNight(page));
test.afterEach(({ page }) => assertNightQuiet(page));
for (const width of [390, 1440])
  test(`清空流日日期只提示选择，恢复后今日安排不变 ${width}`, async ({ page }, info) => {
    await page.clock.setFixedTime(new Date('2026-10-21T07:15:00+08:00'));
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(
      (value) => localStorage.setItem('mingjing-theme', value),
      width === 390 ? 'dark' : 'light',
    );
    await openNight(page, 'today');
    const today = page.locator('[data-runtime="night-today"]'),
      input = page.getByLabel('查看哪天的流日', { exact: true });
    await expect(today).toHaveAttribute('data-load-state', 'ready');
    const plans = today.getByRole('list', { name: '安排与提醒列表', exact: true }),
      original = await plans.innerText();
    await input.fill('');
    await expect(today).toHaveAttribute('data-load-state', 'invalid');
    await expect(today).toHaveAttribute('data-today', '2026-10-21');
    await expect(input).toHaveAttribute('aria-invalid', 'true');
    await expect(today.locator('#today-date-hint')).toHaveText('请先选择日期，再查看这一天的流日。');
    await expect(today.getByRole('button', { name: '重试流日', exact: true })).toHaveCount(0);
    await expect(today.getByRole('alert')).toHaveCount(0);
    await expect(today.locator('[data-daily-system]')).toHaveCount(0);
    expect(await plans.innerText()).toBe(original);
    await auditNight(page);
    const folder = process.env.NIGHT_EVIDENCE_DIR ?? 'evidence/2026-10-21/today-input';
    await fs.mkdir(folder, { recursive: true });
    const capture = async (name: string) => {
      await page.evaluate(() => window.scrollTo(0, 0));
      const file = path.join(folder, `${name}-${width}.png`);
      await fs.writeFile(file, await page.screenshot({ fullPage: true, animations: 'disabled' }), { flag: 'wx' });
      info.annotations.push({ type: 'input_screenshot', description: file.replaceAll('\\', '/') });
    };
    await capture('today-date-cleared');
    await today.getByRole('button', { name: '看今天的流日', exact: true }).click();
    await expect(input).toHaveValue('2026-10-21');
    await expect(today).toHaveAttribute('data-load-state', 'ready');
    await expect(input).not.toHaveAttribute('aria-invalid');
    await expect(today.locator('[data-daily-system]')).toHaveCount(3);
    expect(await plans.innerText()).toBe(original);
    await auditNight(page);
    await capture('today-date-restored');
  });
