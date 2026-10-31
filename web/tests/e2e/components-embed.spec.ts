import { test, expect } from '@playwright/test';
import {
  assertEmbedSafe,
  auditEmbed,
  captureEmbed,
  installViewportSimulation,
  openLiveChat,
  patchViewport,
  prepareEmbed,
  safeArea,
} from './components-embed-helpers';

// UA, CDP insets and VisualViewport below are browser simulations, never Feishu device acceptance.
test.beforeEach(async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await prepareEmbed(page, request);
});
test.afterEach(async ({ page, request }, info) => {
  await assertEmbedSafe(page, request, info.testId);
});

test('模拟浏览器安全区：竖屏底部34与横屏两侧44均不遮住输入和导航', async ({ page }) => {
  const session = await safeArea(page, 34);
  await openLiveChat(page);
  const nav = page.getByRole('navigation', { name: '底部导航' });
  const input = page.getByRole('textbox', { name: '和明镜说说', exact: true });
  await expect.poll(async () => (await nav.boundingBox())!.height).toBeCloseTo(98, 0);
  const portrait = await nav.boundingBox();
  const composer = await page.locator('.composer').boundingBox();
  expect(composer!.y + composer!.height).toBeLessThanOrEqual(portrait!.y + 1);
  const inputRect = await input.boundingBox();
  expect(inputRect!.y + inputRect!.height).toBeLessThanOrEqual(portrait!.y);
  await auditEmbed(page, 'browser-portrait-safe-area');
  await captureEmbed(page, 'browser-safe-area-390');

  await page.setViewportSize({ width: 844, height: 390 });
  await session.send('Emulation.setSafeAreaInsetsOverride', { insets: { top: 0, left: 44, right: 44, bottom: 21 } });
  await expect.poll(async () => (await nav.boundingBox())!.height).toBeCloseTo(85, 0);
  const horizontal = await input.boundingBox();
  const bottomNav = await nav.boundingBox();
  expect(horizontal!.x).toBeGreaterThanOrEqual(44);
  expect(horizontal!.x + horizontal!.width).toBeLessThanOrEqual(800);
  expect(horizontal!.y + horizontal!.height).toBeLessThanOrEqual(bottomNav!.y);
  const firstLink = await nav.getByRole('link').first().boundingBox();
  const lastLink = await nav.getByRole('link').last().boundingBox();
  expect(firstLink!.x).toBeGreaterThanOrEqual(44);
  expect(lastLink!.x + lastLink!.width).toBeLessThanOrEqual(800);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await captureEmbed(page, 'browser-landscape-safe-area-844');
});

test('模拟VisualViewport：键盘420与偏移120保持输入可见，缩放和失焦不误判', async ({ page }) => {
  await installViewportSimulation(page);
  await openLiveChat(page);
  const input = page.getByRole('textbox', { name: '和明镜说说', exact: true });
  const shell = page.locator('.shell');
  const nav = page.getByRole('navigation', { name: '底部导航' });
  await patchViewport(page, { height: 420, offsetTop: 0, scale: 1 });
  await input.focus();
  await input.fill('仅用于键盘仿真的合成草稿');
  await expect(shell).toHaveAttribute('data-keyboard', 'open');
  await expect(nav).toBeHidden();
  await expect
    .poll(async () => {
      const box = (await input.boundingBox())!;
      return box.y + box.height;
    })
    .toBeLessThanOrEqual(420);
  await captureEmbed(page, 'keyboard-height420-offset0');

  await patchViewport(page, { offsetTop: 120 });
  await expect.poll(async () => (await shell.boundingBox())!.y).toBeCloseTo(120, 0);
  const shifted = (await input.boundingBox())!;
  expect(shifted.y).toBeGreaterThanOrEqual(120);
  expect(shifted.y + shifted.height).toBeLessThanOrEqual(540);
  await captureEmbed(page, 'keyboard-height420-offset120');

  await patchViewport(page, { scale: 1.5 });
  await expect(shell).not.toHaveAttribute('data-keyboard');
  await expect(nav).toBeVisible();
  await patchViewport(page, { scale: 1, offsetTop: 0 });
  await expect(shell).toHaveAttribute('data-keyboard', 'open');
  await input.blur();
  await expect(shell).not.toHaveAttribute('data-keyboard');
  await expect(nav).toBeVisible();
  await expect(input).toHaveValue('仅用于键盘仿真的合成草稿');
});

test('浏览器返回先关Panel再回对话保留草稿，前进不重开旧Panel', async ({ page }) => {
  await openLiveChat(page);
  await page.getByRole('textbox', { name: '和明镜说说' }).fill('导航往返保留这段合成草稿');
  await page.getByRole('navigation', { name: '底部导航' }).getByRole('link', { name: '我', exact: true }).click();
  await expect(page).toHaveURL(/#\/me$/);
  const trigger = page.getByRole('button', { name: '更多页面' });
  await trigger.click();
  const dialog = page.getByRole('dialog', { name: '去哪里看看' });
  await expect(dialog).toBeVisible();
  await auditEmbed(page, 'browser-more-pages-panel');
  await captureEmbed(page, 'browser-more-pages-panel');
  await page.goBack();
  await expect(dialog).toHaveCount(0);
  await expect(page).toHaveURL(/#\/me$/);
  await expect(trigger).toBeFocused();
  await page.goBack();
  await expect(page).toHaveURL(/#\/chat$/);
  await expect(page.getByRole('textbox', { name: '和明镜说说' })).toHaveValue('导航往返保留这段合成草稿');
  await page.goForward();
  await expect(page).toHaveURL(/#\/me$/);
  await page.goForward();
  await expect(page).toHaveURL(/#\/me$/);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await captureEmbed(page, 'browser-forward-panel-inert');
});

for (const dismissal of ['Escape', '关闭'] as const) {
  test(`Panel用${dismissal}关闭只消耗自己的历史记录`, async ({ page }) => {
    await openLiveChat(page);
    await page.getByRole('navigation', { name: '底部导航' }).getByRole('link', { name: '我', exact: true }).click();
    const trigger = page.getByRole('button', { name: '更多页面' });
    await trigger.click();
    const dialog = page.getByRole('dialog', { name: '去哪里看看' });
    await expect(dialog).toBeVisible();
    if (dismissal === 'Escape') await page.keyboard.press('Escape');
    else await dialog.getByRole('button', { name: '关闭', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page).toHaveURL(/#\/me$/);
    await expect(trigger).toBeFocused();
    await expect.poll(() => page.evaluate(() => Boolean(history.state?.__mingjing_panel))).toBe(false);
    await page.goBack();
    await expect(page).toHaveURL(/#\/chat$/);
  });
}

test('Panel内部路由链接关闭弹层且不误退刚到达的设置页', async ({ page }) => {
  await openLiveChat(page);
  await page.getByRole('navigation', { name: '底部导航' }).getByRole('link', { name: '我', exact: true }).click();
  await page.getByRole('button', { name: '更多页面' }).click();
  const dialog = page.getByRole('dialog', { name: '去哪里看看' });
  await dialog.getByRole('link', { name: '设置', exact: true }).click();
  await expect(page).toHaveURL(/#\/settings$/);
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('main', { name: '设置', exact: true })).toBeVisible();
  await page.evaluate(
    () => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))),
  );
  await expect(page).toHaveURL(/#\/settings$/);
  await captureEmbed(page, 'browser-panel-route-to-settings');
  await page.goBack();
  await expect(page).toHaveURL(/#\/me$/);
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test.describe('Feishu UA仿真（未做飞书真机验证）', () => {
  test.use({
    userAgent:
      'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Feishu/7.35.5',
  });
  for (const theme of ['light', 'dark'] as const) {
    test(`仿真${theme}主题隐藏重复顶栏，设置可达、键盘不扣52且Panel无AA问题`, async ({ page }) => {
      await installViewportSimulation(page);
      await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
      await page.goto('/#/me');
      await expect(page.locator('.shell')).toHaveAttribute('data-host', 'feishu');
      await expect(page.locator('.topbar')).toBeHidden();
      await expect(page.getByRole('main', { name: '关于我', exact: true })).toBeVisible();
      const settings = page.getByRole('link', { name: '设置', exact: true });
      await expect(settings).toBeVisible();
      await auditEmbed(page, `feishu-${theme}-main`);
      await settings.click();
      await expect(page).toHaveURL(/#\/settings$/);
      await expect(page.getByRole('main', { name: '设置', exact: true })).toBeVisible();
      await captureEmbed(page, `feishu-${theme}-settings`);
      await page.getByRole('navigation', { name: '底部导航' }).getByRole('link', { name: '对话', exact: true }).click();
      const input = page.getByRole('textbox', { name: '和明镜说说' });
      await expect(input).toBeVisible();
      await patchViewport(page, { height: 420, offsetTop: 0, scale: 1 });
      await input.focus();
      await expect(page.locator('.shell')).toHaveAttribute('data-keyboard', 'open');
      await expect.poll(async () => (await page.locator('.chat-page').boundingBox())!.height).toBeCloseTo(420, 0);
      await expect.poll(async () => (await page.locator('.chat-page').boundingBox())!.y).toBeCloseTo(0, 0);
      const box = (await input.boundingBox())!;
      expect(box.y + box.height).toBeLessThanOrEqual(420);
      await expect(page.getByRole('navigation', { name: '底部导航' })).toBeHidden();
      await captureEmbed(page, `feishu-${theme}-keyboard420`);
      // The calendar preview opens a real shared Panel without requesting profile-dependent charts.
      await page.goto('/?components=demo#/today');
      await page.getByRole('button', { name: '查看本月日历', exact: true }).click();
      await expect(page.getByRole('dialog', { name: '本月日历', exact: true })).toBeVisible();
      await auditEmbed(page, `feishu-${theme}-calendar-panel`);
      await captureEmbed(page, `feishu-${theme}-calendar-panel`);
    });
  }
});
