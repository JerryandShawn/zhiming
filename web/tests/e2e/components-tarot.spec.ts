import { test, expect } from '@playwright/test';
import { assertDemoQuiet, captureComponent, guardDemo, openDemo } from './components-helpers';

test.beforeEach(({ page }) => guardDemo(page));
test.afterEach(({ page }) => assertDemoQuiet(page));

test('手机78张不透明牌背保持六列，方向键跨行和已选空位，选满后锁定', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openDemo(page, 'tarot?spread=reflect3&step=pick');
  const grid = page.getByRole('group', { name: '亲手点选牌背' });
  const cards = grid.getByRole('button');
  await expect(cards).toHaveCount(78);
  expect(
    await grid.locator('img').evaluateAll((images) => new Set(images.map((image) => image.getAttribute('src'))).size),
  ).toBe(1);
  await expect(grid.locator('img:not([alt=""])')).toHaveCount(0);
  await cards.nth(0).focus();
  await page.keyboard.press('ArrowDown');
  await expect(cards.nth(6)).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(cards.nth(6)).toBeDisabled();
  await expect(cards.nth(7)).toBeFocused();
  await page.keyboard.press('Home');
  await expect(cards.nth(0)).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(cards.nth(12)).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(cards.nth(13)).toBeFocused();
  await page.keyboard.press('End');
  await expect(cards.nth(77)).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(grid.getByRole('button', { disabled: false })).toHaveCount(0);
  await expect(page.getByRole('status')).toContainText('已选 3 / 3');
  await expect(page.getByRole('button', { name: '查看合成牌阵' })).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await captureComponent(page, 'tarot-picker-selected-390');
});

test('桌面牌背保持十三列，键盘焦点不改变牌面或触发请求', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openDemo(page, 'tarot?spread=choice5&step=pick');
  const cards = page.getByRole('group', { name: '亲手点选牌背' }).getByRole('button');
  await cards.first().focus();
  await page.keyboard.press('ArrowDown');
  await expect(cards.nth(13)).toBeFocused();
  await page.keyboard.press('ArrowRight');
  await expect(cards.nth(14)).toBeFocused();
  await page.keyboard.press('ArrowUp');
  await expect(cards.nth(1)).toBeFocused();
  await expect(page.getByRole('status')).toContainText('已选 0 / 5');
  await captureComponent(page, 'tarot-picker-keyboard-1440');
});

test('普通动效逐张揭开，全部揭开按90毫秒错开且保留逆位', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.setViewportSize({ width: 390, height: 844 });
  await openDemo(page, 'tarot?spread=choice5&step=reveal');
  await expect(page.locator('.tarot-flip-front')).toHaveCount(0);
  const first = page.getByRole('button', { name: '揭开第1张牌', exact: true });
  await first.click();
  await expect(page.locator('.tarot-flip-front')).toHaveCount(1);
  await expect(page.locator('.tarot-flip').first()).toHaveAttribute('data-reduced-motion', 'false');
  expect(
    await page
      .locator('.tarot-flip-rotor')
      .first()
      .evaluate((element) => getComputedStyle(element).transitionDuration),
  ).toBe('0.6s');
  await page.getByRole('button', { name: '全部揭开', exact: true }).click();
  await expect(page.locator('.tarot-flip-front')).toHaveCount(5);
  expect(
    await page
      .locator('.tarot-flip')
      .evaluateAll((elements) =>
        elements.map((element) => (element as HTMLElement).style.getPropertyValue('--tarot-reveal-delay')),
      ),
  ).toEqual(['0ms', '90ms', '180ms', '270ms', '360ms']);
  await expect(page.locator('.tarot-flip-front.reversed')).toHaveCount(1);
  await page
    .locator('.tarot-flip-rotor')
    .last()
    .evaluate((element) => Promise.all(element.getAnimations().map((animation) => animation.finished)));
  expect(
    await page
      .locator('.tarot-flip-rotor')
      .last()
      .evaluate((element) => getComputedStyle(element).transform),
  ).toBe('matrix3d(-1, 0, 0, 0, 0, 1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 1)');
  await captureComponent(page, 'tarot-choice5-flipped-390', true);
});

test('减少动效模式直接呈现全部固定牌面，无过渡与错开延迟', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openDemo(page, 'tarot?spread=reflect3&step=reveal');
  await page.getByRole('button', { name: '全部揭开', exact: true }).click();
  await expect(page.locator('.tarot-flip-front')).toHaveCount(3);
  expect(
    await page
      .locator('.tarot-flip-rotor')
      .evaluateAll((elements) => elements.map((element) => getComputedStyle(element).transitionDuration)),
  ).toEqual(['0s', '0s', '0s']);
  expect(
    await page
      .locator('.tarot-flip')
      .evaluateAll((elements) =>
        elements.map((element) => (element as HTMLElement).style.getPropertyValue('--tarot-reveal-delay')),
      ),
  ).toEqual(['0ms', '0ms', '0ms']);
  await captureComponent(page, 'tarot-reduced-motion-390');
});
