import { test, expect } from '@playwright/test';
import { assertDemoQuiet, captureComponent, guardDemo, openDemo } from './components-helpers';

test.beforeEach(({ page }) => guardDemo(page));
test.afterEach(({ page }) => assertDemoQuiet(page));

test('命盘时辰口径默认真太阳，差异并列北京时间，大运可解释并回焦', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openDemo(page, 'chart?tab=bazi');
  const basis = page.getByRole('region', { name: '时辰口径核对' });
  await expect(basis.getByRole('heading', { name: '真太阳时', exact: true })).toBeVisible();
  await expect(basis.getByRole('heading', { name: '按北京时间则为' })).toBeVisible();
  await expect(basis).toContainText('时柱 甲辰');
  await expect(basis).toContainText('时柱 乙巳');
  const luck = page.getByRole('button', { name: /^查看.*大运解释/ }).first();
  await luck.click();
  await expect(page.getByRole('dialog')).toContainText('不是这十年会发生什么的预测');
  await captureComponent(page, 'chart-luck-explanation-390');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(luck).toBeFocused();
});

test('手机紫微默认十二宫列表，切网格只在容器内横滚', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await openDemo(page, 'chart?tab=ziwei');
  const list = page.getByRole('region', { name: '十二宫列表', exact: true });
  await expect(list.locator('details')).toHaveCount(12);
  await list.locator('summary').first().click();
  await expect(list.locator('details').first()).toHaveAttribute('open', '');
  await page.getByRole('button', { name: '网格', exact: true }).click();
  const grid = page.getByRole('region', { name: '十二宫网格，可左右滚动' });
  await expect(grid.locator('[data-palace-branch]')).toHaveCount(12);
  expect(await grid.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await captureComponent(page, 'chart-palace-grid-375');
  await page.getByRole('button', { name: '宫位列表', exact: true }).click();
  await expect(list).toBeVisible();
});

test('桌面紫微四乘四周边十二宫，中间信息不挤占宫位', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openDemo(page, 'chart?tab=ziwei');
  const grid = page.locator('.chart-palace-grid');
  await expect(grid).toBeVisible();
  const cells = await grid.locator('[data-palace-branch]').evaluateAll((elements) =>
    elements.map((element) => {
      const style = getComputedStyle(element);
      return `${style.gridColumnStart}:${style.gridRowStart}`;
    }),
  );
  expect(new Set(cells).size).toBe(12);
  expect(cells).not.toEqual(expect.arrayContaining(['2:2', '3:2', '2:3', '3:3']));
  const center = await grid.locator('.chart-palace-center').evaluate((element) => {
    const style = getComputedStyle(element);
    return [style.gridColumnStart, style.gridColumnEnd, style.gridRowStart, style.gridRowEnd];
  });
  expect(center).toEqual(['2', '4', '2', '4']);
  const trigger = grid.getByRole('button', { name: /^查看命宫宫位依据/ });
  await trigger.click();
  await expect(page.getByRole('dialog')).toContainText('紫微');
  await expect(page.getByRole('dialog')).toContainText('对宫：迁移');
  await captureComponent(page, 'chart-palace-explanation-1440');
  await page.getByRole('button', { name: '关闭', exact: true }).click();
  await expect(trigger).toBeFocused();
});

test('星盘轮保留十颗星体、十二宫头和五条对应相位线', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openDemo(page, 'chart?tab=astro');
  const wheel = page.getByRole('img', { name: /本命星盘轮，10颗星体，5条已返回相位/ });
  await expect(wheel.locator('[data-planet]')).toHaveCount(10);
  await expect(wheel.locator('[data-house]')).toHaveCount(12);
  await expect(wheel.locator('[data-aspect]')).toHaveCount(5);
  await expect(wheel.locator('[data-planet="太阳"]')).toHaveAttribute('data-longitude', '15');
  await expect(wheel.locator('[data-aspect="太阳-月亮"]')).toHaveClass(/tense/);
  await page.getByText('核对轮图角度与相位', { exact: true }).click();
  await expect(page.getByText('太阳 刑相 月亮 · 容许度 0°', { exact: true })).toBeVisible();
  await captureComponent(page, 'chart-astro-angles-390', true);
});
