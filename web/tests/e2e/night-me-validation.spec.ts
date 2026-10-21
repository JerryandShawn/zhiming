import { expect, test } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { assertNightQuiet, auditNight, guardNight, openNight } from './night-helpers';

test.beforeEach(async ({ context, page }) => {
  guardNight(page);
  await context.route('**/*', async (route) => {
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

for (const width of [390, 1440])
  test(`本地422拒绝保留可修正草稿，无需关闭Sheet即可保存 ${width}`, async ({ page }, info) => {
    const theme = width === 390 ? 'dark' : 'light';
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
    await openNight(page, 'me');
    const me = page.locator('[data-runtime="night-me"]'),
      item = me.locator('[data-profile-id="profile-basic"]');
    await expect(me).toHaveAttribute('data-revision', '1');
    await item.getByRole('button', { name: '编辑画像条目：称呼与基本情况', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '修改画像条目', exact: true }),
      input = dialog.getByRole('textbox', { name: '你的说法', exact: true });
    // hasBirthFields detects the key and colon; this is deliberately fictional,
    // never submitted to an API or exposed as the error message.
    const rejected = '出生日期：2099-01-01（合成校验样本）';
    await input.fill(rejected);
    await dialog.getByRole('button', { name: '保存修改', exact: true }).click();
    await expect(dialog.getByRole('alert')).toContainText('尚未保存');
    await expect(dialog.getByRole('alert')).not.toContainText(rejected);
    await expect(input).toBeEditable();
    // Return a boolean so assertion diagnostics do not repeat the raw draft.
    expect(await input.evaluate((node, expected) => (node as HTMLTextAreaElement).value === expected, rejected)).toBe(
      true,
    );
    await expect(me).toHaveAttribute('data-revision', '1');
    await expect(item.getByText('你改过', { exact: true })).toHaveCount(0);
    await expect(dialog.getByRole('button', { name: '用原操作重试', exact: true })).toHaveCount(0);
    const folder = process.env.NIGHT_EVIDENCE_DIR ?? 'evidence/2026-10-21/me-validation';
    await fs.mkdir(folder, { recursive: true });
    const capture = async (state: string) => {
      const file = path.join(folder, `${state}-${width}-${theme}.png`);
      await fs.writeFile(file, await page.screenshot({ fullPage: true, animations: 'disabled' }), { flag: 'wx' });
      info.annotations.push({ type: 'validation_screenshot', description: file.replaceAll('\\', '/') });
    };
    await auditNight(page);
    await capture('me-422-editable');
    const safe = '我已把这一条修正为安全的合成画像摘要。';
    await input.fill(safe);
    await dialog.getByRole('button', { name: '保存修改', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(item).toContainText(safe);
    await expect(item.getByText('你改过', { exact: true })).toBeVisible();
    await expect(me).toHaveAttribute('data-revision', '2');
    await expect(me.getByRole('status')).toContainText('修改已确认。');
    await auditNight(page);
    await capture('me-422-corrected-saved');
  });
