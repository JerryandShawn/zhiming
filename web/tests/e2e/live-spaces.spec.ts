import { expect, test, type Page } from '@playwright/test';

const activity = new WeakMap<Page, string[]>();

async function open(page: Page) {
  await page.goto('/?spaces=demo#/spaces?space=career');
  await expect(page.locator('[data-page="spaces"][data-runtime="spaces-fake"]')).toBeVisible();
  await expect(page.getByRole('heading', { name: '事业的话题', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '合成样例：是否换岗', exact: true })).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  const requests: string[] = [];
  activity.set(page, requests);
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith('/api/')) requests.push(`${request.method()} ${url.pathname}`);
    if (['http:', 'https:'].includes(url.protocol) && url.origin !== 'http://127.0.0.1:4173')
      requests.push(`external ${url.origin}`);
  });
});

test.afterEach(async ({ page }) => {
  expect(activity.get(page)).toEqual([]);
});

test('新建话题只显示程序回执确认的结果，刷新后合成数据还原', async ({ page }) => {
  await open(page);
  await page.getByRole('textbox', { name: '新话题名称', exact: true }).fill('合成新话题');
  await page.getByRole('button', { name: '新建话题', exact: true }).click();
  await expect(page.getByText('新建话题已保存。', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '合成新话题', exact: true })).toBeVisible();
  await expect(page.getByRole('textbox', { name: '新话题名称', exact: true })).toHaveValue('');
  await page.reload();
  await expect(page.getByRole('heading', { name: '事业的话题', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '合成新话题', exact: true })).toHaveCount(0);
});

test('改名保留原话题，取消不改变标题', async ({ page }) => {
  await open(page);
  await page.getByRole('button', { name: '改名：合成样例：是否换岗', exact: true }).click();
  const input = page.getByRole('textbox', { name: '新的话题名：合成样例：是否换岗', exact: true });
  await input.fill('换岗决策');
  await page.getByRole('button', { name: '保存', exact: true }).click();
  await expect(page.getByText('改名已保存。', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '换岗决策', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '改名：换岗决策', exact: true }).click();
  await page.getByRole('textbox', { name: '新的话题名：换岗决策', exact: true }).fill('未保存的名字');
  await page.getByRole('button', { name: '取消', exact: true }).click();
  await expect(page.getByRole('heading', { name: '换岗决策', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '未保存的名字', exact: true })).toHaveCount(0);
});

test('归档话题进入折叠区并可恢复', async ({ page }) => {
  await open(page);
  await page.getByRole('button', { name: '归档：合成样例：是否换岗', exact: true }).click();
  await expect(page.getByText('归档已保存。', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '合成样例：是否换岗', exact: true })).toHaveCount(0);
  const archived = page.locator('summary').filter({ hasText: '已归档 2 个' });
  await archived.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: '合成样例：是否换岗', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '恢复：合成样例：是否换岗', exact: true }).click();
  await expect(page.getByText('恢复已保存。', { exact: true })).toBeVisible();
  await expect(page.locator('.live-topic-list').first()).toContainText('合成样例：是否换岗');
});

test('移动话题后从原区消失并出现在目标区', async ({ page }) => {
  await open(page);
  await page.getByRole('combobox', { name: '移动「合成样例：是否换岗」到', exact: true }).selectOption('daily');
  await expect(page.getByText('移动已保存。', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '合成样例：是否换岗', exact: true })).toHaveCount(0);
  await page.getByRole('navigation', { name: '区', exact: true }).getByRole('link', { name: '日常', exact: true }).click();
  await expect(page.getByRole('heading', { name: '日常的话题', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '合成样例：是否换岗', exact: true })).toBeVisible();
  await expect(page.getByRole('combobox', { name: '移动「合成样例：是否换岗」到', exact: true })).toHaveValue('daily');
});

test('敏感区有可访问名称，键盘可切换区并保留页面主标题', async ({ page }) => {
  await open(page);
  await expect(page.getByRole('img', { name: '敏感区', exact: true })).toHaveCount(2);
  const relationships = page
    .getByRole('navigation', { name: '区', exact: true })
    .getByRole('link', { name: '敏感区 感情', exact: true });
  await relationships.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: '感情的话题', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '区与话题', exact: true })).toBeVisible();
  await expect(page.getByText('敏感区 · 读取和写入都按当前用途授权核对。', { exact: true })).toBeVisible();
});
