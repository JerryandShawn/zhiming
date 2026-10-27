import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import { prepareLegacy } from './fixture';

const evidence = path.resolve(process.env.LEGACY_EVIDENCE_DIR ?? 'evidence/2026-10-27/legacy-browser-first');
for (const width of [390, 1440]) {
  test(`old page consumes card and four receipt events without writes ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const f = await prepareLegacy(page, 'catalog');
    await page.getByRole('textbox', { name: '本次问题' }).fill('合成事件兼容');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    const answer = page.locator('#chatFlow .msg-ai .msg-body').last();
    await expect(answer).toContainText(f.finalText);
    await expect(answer).toContainText('你想先梳理哪件事？');
    await expect(answer).toContainText('可以在输入框补充回答');
    await expect(answer).not.toContainText('复核中');
    await expect(answer).not.toContainText('已修订');
    await expect(answer).not.toContainText('本轮已保存');
    await expect(answer).not.toContainText('date_calc');
    await expect(page.getByRole('button', { name: '停止回答' })).toBeHidden();
    expect(f.cursors).toEqual([null]);
    expect(f.writes).toEqual(['POST /api/chat']);
    expect(f.outside).toEqual([]);
    expect(f.errors).toEqual([]);
    const axe = await new AxeBuilder({ page }).analyze();
    expect(axe.violations).toEqual([]);
    await fs.mkdir(evidence, { recursive: true });
    await fs.writeFile(path.join(evidence, `catalog-axe-${width}.json`), JSON.stringify(axe.violations));
    await page.screenshot({ path: path.join(evidence, `catalog-${width}.png`), fullPage: true });
  });
}
for (const width of [375, 390, 768, 1440])
  for (const colorScheme of ['light', 'dark'] as const) {
    test(`old page live partial → revised final ${width} ${colorScheme} system preference`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 1440 ? 900 : 844 });
      await page.emulateMedia({ colorScheme });
      const f = await prepareLegacy(page);
      await page.getByRole('textbox', { name: '本次问题' }).fill('合成流式测试');
      await page.getByRole('button', { name: '发送', exact: true }).click();
      const answer = page.locator('#chatFlow .msg-ai .msg-body').last();
      await expect(answer).toContainText(f.firstText);
      await expect(answer).toContainText('复核中');
      await expect(page.getByRole('button', { name: '停止回答' })).toBeVisible();
      await fs.mkdir(evidence, { recursive: true });
      await page.screenshot({ path: path.join(evidence, `partial-${width}-${colorScheme}.png`), fullPage: true });
      f.release();
      await expect(answer).toContainText(f.finalText);
      await expect(answer).toContainText('已修订');
      await expect(answer).not.toContainText(f.firstText);
      await expect(answer).not.toContainText('复核中');
      await expect(page.getByRole('button', { name: '停止回答' })).toBeHidden();
      const axe = await new AxeBuilder({ page }).analyze();
      await fs.writeFile(
        path.join(evidence, `axe-${width}-${colorScheme}.json`),
        JSON.stringify(axe.violations, null, 2),
      );
      expect(axe.violations).toEqual([]);
      await page.screenshot({ path: path.join(evidence, `final-${width}-${colorScheme}.png`), fullPage: true });
      expect(f.cursors).toEqual([null, '2']);
      expect(f.writes).toEqual(['POST /api/chat']);
      expect(f.outside).toEqual([]);
      expect(f.errors).toEqual([]);
    });
  }
for (const width of [390, 1440]) {
  test(`old page stop retains partial and confirms interrupted ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const f = await prepareLegacy(page, 'cancelled');
    await page.getByRole('textbox', { name: '本次问题' }).fill('合成停止测试');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    const answer = page.locator('#chatFlow .msg-ai .msg-body').last();
    await expect(answer).toContainText(f.firstText);
    const started = Date.now();
    await page.getByRole('button', { name: '停止回答' }).click();
    await expect(answer).toContainText('已中断', { timeout: 2000 });
    expect(Date.now() - started).toBeLessThan(2000);
    await expect(answer).toContainText(f.firstText);
    await expect(answer).not.toContainText(f.finalText);
    await fs.mkdir(evidence, { recursive: true });
    await page.screenshot({ path: path.join(evidence, `interrupted-${width}.png`), fullPage: true });
    expect(f.writes).toEqual(['POST /api/chat', 'POST /api/runs/synthetic-legacy-browser/cancel']);
    expect(f.outside).toEqual([]);
    expect(f.errors).toEqual([]);
  });
  test(`old stream flag-off remains compatible ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const f = await prepareLegacy(page, 'legacy');
    await page.getByRole('textbox', { name: '本次问题' }).fill('合成旧格式');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await expect(page.locator('#chatFlow .msg-ai').last()).toContainText('旧格式完整回答');
    expect(f.cursors).toEqual([]);
    expect(f.writes).toEqual(['POST /api/chat']);
    expect(f.outside).toEqual([]);
    expect(f.errors).toEqual([]);
  });
}
test('bad accepted URL stays local and preserves the original retry operation', async ({ page }) => {
  const f = await prepareLegacy(page, 'bad-receipt');
  await page.getByRole('textbox', { name: '本次问题' }).fill('合成回执测试');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.locator('#chatFlow .err-banner')).toContainText('回执尚未核对');
  expect(f.cursors).toEqual([]);
  expect(f.writes).toEqual(['POST /api/chat']);
  expect(f.outside).toEqual([]);
  expect(f.errors).toEqual([]);
});
