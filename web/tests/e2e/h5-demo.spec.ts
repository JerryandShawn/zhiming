import { test, expect, type Page } from '@playwright/test';
import fs from 'node:fs/promises';
import { guardNight, assertNightQuiet, auditNight } from './night-helpers';
import { installViewportSimulation, patchViewport, safeArea } from './components-embed-helpers';

const evidence = process.env.H5_EVIDENCE_DIR ?? 'test-results/h5-demo-latest';
test.use({ userAgent: 'Mozilla/5.0 Synthetic Feishu/7.0' });
test.beforeEach(async ({ page }) => {
  guardNight(page);
  await page.route('**/*', (route) => {
    const request = route.request(),
      url = new URL(request.url());
    return request.method() !== 'GET' || url.origin !== 'http://127.0.0.1:4173' || url.pathname.startsWith('/api/')
      ? route.abort()
      : route.continue();
  });
});
test.afterEach(async ({ page }) => {
  assertNightQuiet(page);
  expect(
    await page.evaluate(() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)])),
  ).not.toMatch(/synthetic-(?:code|session)|SECRET_ONE_TIME|合成访客/);
});
async function capture(page: Page, name: string) {
  await auditNight(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await fs.mkdir(evidence, { recursive: true });
  await page.screenshot({ path: `${evidence}/${name}.png`, fullPage: true });
}
for (const [width, height] of [
  [375, 812],
  [390, 844],
  [768, 1024],
  [1440, 900],
])
  for (const theme of ['light', 'dark']) {
    test(`H5 synthetic sign-in visual ${width} ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
      await page.goto('/?embed=demo#/chat');
      await expect(page.locator('[data-demo="h5"]')).toHaveAttribute('data-host', 'feishu');
      await expect(page.getByRole('dialog', { name: '登录' })).toHaveCount(0);
      await expect(page.getByRole('status')).toContainText('还没有开始登录');
      await page.evaluate(() => document.fonts.ready);
      const draft = page.getByRole('textbox', { name: '本地草稿' });
      await draft.fill('留在本页的合成草稿');
      await capture(page, `idle-${width}-${theme}`);
      await page.getByRole('button', { name: '开始模拟登录' }).click();
      await expect(page.getByRole('status')).toContainText('模拟会话已确认');
      await expect(draft).toBeFocused();
      await expect(page.getByText('你好，合成访客。', { exact: false })).toBeVisible();
      await capture(page, `ready-${width}-${theme}`);
      await page.getByRole('button', { name: '模拟会话失效' }).click();
      await expect(page.getByRole('status')).toContainText('模拟会话已失效');
      await expect(draft).toHaveValue('留在本页的合成草稿');
      await expect(page.getByRole('button', { name: '开始模拟登录' })).toBeFocused();
      await expect(page.getByText('你好，合成访客。', { exact: false })).toHaveCount(0);
      await capture(page, `expired-${width}-${theme}`);
    });
  }

for (const [scenario, expected] of [
  ['denied', '没有同意授权'],
  ['unavailable', '暂时没有连上'],
  ['timeout', '等待已超时'],
  ['expired', '模拟会话已失效'],
]) {
  test(`H5 controlled ${scenario} keeps draft and restarts with a fresh flow`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/?embed=demo#/chat');
    const draft = page.getByRole('textbox', { name: '本地草稿' });
    await draft.fill('失败后保留的合成草稿');
    await page.getByLabel('预览情形').selectOption(scenario);
    await page.getByRole('button', { name: '开始模拟登录' }).click();
    await expect(page.getByRole('status')).toContainText(expected, { timeout: 10000 });
    await expect(draft).toHaveValue('失败后保留的合成草稿');
    await capture(page, `failure-${scenario}`);
    await page.getByLabel('预览情形').selectOption('success');
    await page.getByRole('button', { name: '开始模拟登录' }).click();
    await expect(page.getByRole('status')).toContainText('模拟会话已确认');
  });
}

test('H5 cancellation, sign-out and keyboard-only restart remain local', async ({ page }) => {
  await page.goto('/?embed=demo#/chat');
  const draft = page.getByRole('textbox', { name: '本地草稿' });
  await draft.fill('返回后继续的合成草稿');
  await page.getByLabel('预览情形').selectOption('timeout');
  await page.getByRole('button', { name: '开始模拟登录' }).click();
  await page.getByRole('button', { name: '取消登录' }).click();
  await expect(page.getByRole('status')).toContainText('还没有开始登录');
  await expect(page.getByRole('button', { name: '开始模拟登录' })).toBeFocused();
  await page.getByLabel('预览情形').selectOption('success');
  const start = page.getByRole('button', { name: '开始模拟登录' });
  await start.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('status')).toContainText('模拟会话已确认');
  await page.getByRole('button', { name: '退出模拟会话' }).click();
  await expect(page.getByRole('status')).toContainText('已在本页退出');
  await expect(start).toBeFocused();
  await expect(draft).toHaveValue('返回后继续的合成草稿');
  await capture(page, 'signed-out-keyboard');
  await page.reload();
  await expect(page.getByRole('status')).toContainText('还没有开始登录');
  await expect(draft).toHaveValue('');
});

test('H5 safe area, simulated keyboard and browser return preserve the isolated draft', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installViewportSimulation(page);
  await safeArea(page, 34);
  await page.goto('/?embed=demo#/chat');
  const draft = page.getByRole('textbox', { name: '本地草稿' });
  await draft.fill('仅在本页的键盘草稿');
  await patchViewport(page, { height: 420, offsetTop: 120, scale: 1 });
  await expect(page.locator('[data-demo="h5"]')).toHaveAttribute('data-keyboard', 'open');
  await expect
    .poll(async () => {
      const rect = (await draft.boundingBox())!;
      return rect.y + rect.height;
    })
    .toBeLessThanOrEqual(540);
  expect((await draft.boundingBox())!.y).toBeGreaterThanOrEqual(120);
  await capture(page, 'keyboard-safe-area');
  await draft.blur();
  await expect(page.locator('[data-demo="h5"]')).not.toHaveAttribute('data-keyboard', 'open');
  await page.evaluate(() => {
    location.hash = '#/settings';
  });
  await expect(page).toHaveURL(/#\/settings$/);
  await page.goBack();
  await expect(page).toHaveURL(/#\/chat$/);
  await expect(draft).toHaveValue('仅在本页的键盘草稿');
  await expect(page.getByRole('status')).toContainText('还没有开始登录');
  await capture(page, 'browser-return');
});
