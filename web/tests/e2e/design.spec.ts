import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

for (const width of [375, 390, 768, 1440])
  for (const theme of ['light', 'dark']) {
    test(`design gallery ${theme} ${width}`, async ({ page }) => {
      await page.setViewportSize({
        width,
        height: width === 1440 ? 900 : width === 768 ? 1024 : width === 390 ? 844 : 812,
      });
      await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
      await page.goto('/#/__design');
      await expect(page.locator('[data-page="__design"]')).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      const directory = path.resolve('../docs/v4/evidence/P10/components');
      await fs.mkdir(directory, { recursive: true });
      await page.screenshot({
        path: path.join(directory, `design-${theme}-${width}.png`),
        fullPage: true,
        animations: 'disabled',
      });
      await page.getByRole('button', { name: '主操作', exact: true }).focus();
      await expect(page.getByRole('button', { name: '主操作', exact: true })).toBeFocused();
      const focus = await page.getByRole('button', { name: '主操作', exact: true }).evaluate((element) => ({
        style: getComputedStyle(element).outlineStyle,
        width: getComputedStyle(element).outlineWidth,
      }));
      expect(focus.style).not.toBe('none');
      expect(parseFloat(focus.width)).toBeGreaterThanOrEqual(2);
    });
  }

for (const width of [390, 1440])
  for (const theme of ['light', 'dark']) {
    test(`overlay states ${theme} ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
      await page.goto('/#/__design');
      await expect(page.locator('[data-page="__design"]')).toBeVisible();
      const directory = path.resolve('../docs/v4/evidence/P10/components');
      await page.getByRole('button', { name: '打开对话框' }).click();
      await page.screenshot({ path: path.join(directory, `dialog-${theme}-${width}.png`), animations: 'disabled' });
      await page.keyboard.press('Escape');
      await page.getByRole('button', { name: '打开抽屉' }).click();
      await page.screenshot({ path: path.join(directory, `sheet-${theme}-${width}.png`), animations: 'disabled' });
      await page.keyboard.press('Escape');
      await expect(page.getByRole('button', { name: '打开抽屉' })).toBeFocused();
    });
  }
