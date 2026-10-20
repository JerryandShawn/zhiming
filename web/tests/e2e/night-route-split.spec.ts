import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { captureNight } from './night-helpers';
import { cinnabarUsages } from './appearance';

const origin = 'http://127.0.0.1:4173';
const day = { day_ganzhi: '戊辰', method_note: '合成计算依据：保留真实页面的数据呈现与即时查询。' };
async function audit(page: Page) {
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  expect((await page.evaluate(cinnabarUsages)).length).toBeLessThanOrEqual(3);
}
function gate() {
  let resolve!: () => void;
  const promise = new Promise<void>((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
}

async function prepare(page: Page, width: number, authenticated = true) {
  await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
  if (authenticated)
    await page.addInitScript(() => sessionStorage.setItem('mingjing-auth-token', 'synthetic-route-contract'));
  const api: string[] = [],
    unexpected: string[] = [],
    errors: string[] = [],
    scripts: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname.endsWith('.js')) scripts.push(url.pathname);
  });
  await page.route('**/*', async (route) => {
    const request = route.request(),
      url = new URL(request.url());
    if (['http:', 'https:'].includes(url.protocol) && url.origin !== origin) {
      unexpected.push(url.origin);
      return route.abort();
    }
    if (!url.pathname.startsWith('/api/')) return route.continue();
    api.push(url.pathname);
    if (request.method() !== 'GET') {
      unexpected.push(`${request.method()} ${url.pathname}`);
      return route.abort();
    }
    const data =
      url.pathname === '/api/chart'
        ? { day }
        : url.pathname === '/api/cases'
          ? []
          : url.pathname === '/api/history'
            ? [{ id: 'synthetic-history' }]
            : undefined;
    if (!data) {
      unexpected.push(url.pathname);
      return route.abort();
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
  });
  return { api, unexpected, errors, scripts };
}

async function populated(page: Page) {
  await page.goto('/#/today');
  await expect(page.getByRole('heading', { name: day.day_ganzhi, exact: true })).toBeVisible();
  await expect(page.getByText('最近有 1 条对话记录可继续查看。', { exact: true })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

for (const width of [390, 1440]) {
  test(`完整今日保留即时查询，Dialog视图仅交互后加载 ${width}`, async ({ page }) => {
    const activity = await prepare(page, width);
    await populated(page);
    expect([...new Set(activity.api)].sort()).toEqual(['/api/cases', '/api/chart', '/api/history']);
    expect(activity.scripts.filter((path) => /\/(?:DialogContent|LoginDialog)-/.test(path))).toEqual([]);
    await expect(page.getByRole('dialog')).toHaveCount(0);
    if (width === 390) {
      const trigger = page.getByRole('button', { name: '查看本月日历', exact: true });
      await trigger.click();
      await expect(page.getByRole('dialog', { name: '本月日历', exact: true })).toBeVisible();
      expect(activity.scripts.some((path) => /\/DialogContent-/.test(path))).toBe(true);
      await audit(page);
      await captureNight(page, 'Q7-lazy-calendar-390', true);
      await page.keyboard.press('Escape');
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await expect(trigger).toBeFocused();
    } else {
      await expect(page.getByRole('button', { name: '查看本月日历', exact: true })).toHaveCount(0);
      await expect(page.locator('.today-calendar')).toBeVisible();
    }
    await audit(page);
    await captureNight(page, `Q7-filled-today-${width}`, true);
    expect({ unexpected: activity.unexpected, errors: activity.errors }).toEqual({ unexpected: [], errors: [] });
  });
}

test('首次导入尚未结束时Back关闭等待层，迟到模块不会重新打开日历', async ({ page }) => {
  const activity = await prepare(page, 390),
    requested = gate(),
    release = gate();
  await page.route('**/assets/DialogContent-*.js', async (route) => {
    requested.resolve();
    await release.promise;
    await route.continue();
  });
  await populated(page);
  const trigger = page.getByRole('button', { name: '查看本月日历', exact: true });
  try {
    await trigger.click();
    await requested.promise;
    await expect(page.getByRole('status', { name: '正在展开本月日历', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '取消展开', exact: true })).toBeVisible();
    await page.evaluate(() => history.back());
    await expect(page.getByRole('status', { name: '正在展开本月日历', exact: true })).toHaveCount(0);
    await expect(trigger).toBeFocused();
  } finally {
    release.resolve();
  }
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(new URL(page.url()).hash).toBe('#/today');
  await trigger.click();
  await expect(page.getByRole('dialog', { name: '本月日历', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '关闭', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await captureNight(page, 'Q7-canceled-import-retains-today-390', true);
  expect({ unexpected: activity.unexpected, errors: activity.errors }).toEqual({ unexpected: [], errors: [] });
});

test('登录视图延迟加载时业务查询仍关闭，受保护页面仍隐藏', async ({ page }) => {
  const activity = await prepare(page, 390, false),
    requested = gate(),
    release = gate();
  await page.route('**/assets/LoginDialog-*.js', async (route) => {
    requested.resolve();
    await release.promise;
    await route.continue();
  });
  try {
    await page.goto('/#/today', { waitUntil: 'domcontentloaded' });
    await requested.promise;
    await expect(page.getByRole('status', { name: '正在展开登录', exact: true })).toBeVisible();
    await expect(page.locator('.auth-hidden')).toBeHidden();
    expect(activity.api).toEqual([]);
    await captureNight(page, 'Q7-login-loading-390', true);
  } finally {
    release.resolve();
  }
  await expect(page.getByRole('dialog', { name: '登录明镜台', exact: true })).toBeVisible();
  expect(activity.api).toEqual([]);
  await audit(page);
  await captureNight(page, 'Q7-login-ready-390', true);
  expect({ unexpected: activity.unexpected, errors: activity.errors }).toEqual({ unexpected: [], errors: [] });
});
