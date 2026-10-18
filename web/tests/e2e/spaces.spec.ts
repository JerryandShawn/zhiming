import { test, expect, type Page } from '@playwright/test';
import fs from 'node:fs/promises';

const apiRequests = new WeakMap<Page, string[]>();
const card = (page: Page, title: string) => page.getByRole('article', { name: `话题：${title}`, exact: true });
async function choose(page: Page, label: string, option: string) {
  await page.getByRole('combobox', { name: label, exact: true }).click();
  await page.getByRole('option', { name: option, exact: true }).click();
}
async function open(page: Page, route: string) {
  await page.goto(`/?spaces=demo#/${route}`);
  await expect(page.getByRole('region', { name: '功能区模拟说明' })).toBeVisible();
  await expect(page.locator('[data-page]')).toBeVisible();
}
async function saveName(page: Page, name: string, label = '名称') {
  await page.getByRole('textbox', { name: label, exact: true }).fill(name);
  await page.getByRole('button', { name: '保存到草稿', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
}
async function capture(page: Page, name: string) {
  await fs.mkdir('evidence/2026-10-18/spaces/interactions', { recursive: true });
  await page.screenshot({ path: `evidence/2026-10-18/spaces/interactions/${name}.png`, animations: 'disabled' });
}

test.beforeEach(async ({ page }) => {
  const requests: string[] = [];
  apiRequests.set(page, requests);
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (
      url.pathname.startsWith('/api/') ||
      (['http:', 'https:'].includes(url.protocol) && url.origin !== 'http://127.0.0.1:4173')
    )
      requests.push(url.origin + url.pathname);
  });
});
test.afterEach(async ({ page }) => expect(apiRequests.get(page)).toEqual([]));

test('桌面区、话题、对话三栏与全部时间线', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, 'chat?space=career&topic=interview');
  const navigation = page.getByRole('navigation', { name: '功能区', exact: true });
  const topics = page.getByRole('complementary', { name: '话题列表' });
  const conversation = page.getByRole('region', { name: '示例对话' });
  await expect(navigation.getByRole('link')).toHaveCount(8);
  await expect(navigation.getByLabel('2 条未读')).toBeVisible();
  const positions = await Promise.all([navigation.boundingBox(), topics.boundingBox(), conversation.boundingBox()]);
  expect(positions[0]!.x + positions[0]!.width).toBeLessThanOrEqual(positions[1]!.x);
  expect(positions[1]!.x + positions[1]!.width).toBeLessThanOrEqual(positions[2]!.x);
  await expect(page.locator('[data-message]')).toHaveCount(4);
  await page
    .getByRole('navigation', { name: '区内话题' })
    .getByRole('link', { name: /学习计划/ })
    .click();
  await expect(page.locator('[data-message]')).toHaveCount(2);
  await navigation.getByRole('link', { name: /全部/ }).click();
  await expect(page.getByRole('heading', { name: '全部 · 按时间' })).toBeVisible();
  await expect(page.locator('[data-message]')).toHaveCount(18);
  const ids = await page
    .locator('[data-message]')
    .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-message')));
  expect(ids.slice(0, 6)).toEqual(['weekend-1', 'weekend-2', 'i1', 'i2', 'i3', 'i4']);
  await expect(page.getByRole('button', { name: '发送', exact: true })).toBeDisabled();
});

test('手机横滑区标签、话题下拉、输入归属与草稿连续', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, 'chat?space=career&topic=interview');
  const tabs = page.getByRole('navigation', { name: '手机功能区' });
  expect(await tabs.evaluate((node) => node.scrollWidth > node.clientWidth)).toBe(true);
  await expect(tabs.getByRole('img', { name: '敏感区' })).toHaveCount(2);
  await expect(tabs.getByText('事业学业')).toHaveClass(/accent/);
  await page.getByRole('textbox', { name: '本地对话草稿' }).fill('合成试写草稿');
  await choose(page, '当前话题', '学习计划');
  await expect(page.locator('[data-message]')).toHaveCount(2);
  await expect(page.getByRole('textbox', { name: '本地对话草稿' })).toHaveValue('合成试写草稿');
  await page.getByRole('button', { name: /^将归入：/ }).click();
  await choose(page, '主区', '家庭');
  await page.getByRole('button', { name: '确认本地归属' }).click();
  await expect(page.getByRole('button', { name: /^将归入：家庭/ })).toBeVisible();
  await tabs.getByRole('link', { name: /财务/ }).click();
  await expect(page.getByRole('heading', { name: '月度预算' })).toBeVisible();
  await expect(page.getByRole('button', { name: /将归入：财务/ })).toBeVisible();
});

test('回答标签可改区或新建话题，原文保留且刷新重置', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, 'chat?space=all');
  const message = page.locator('[data-message="i2"]');
  const original = '先准备一个你能讲清楚过程与结果的项目例子。';
  await message.getByRole('button', { name: /^归入：/ }).click();
  await choose(page, '主区', '家庭');
  await choose(page, '归入话题', '新建话题…');
  await page.getByRole('button', { name: '确认本地归属' }).click();
  await expect(page.getByRole('alert')).toContainText('新话题需要一个名字');
  await page.getByRole('textbox', { name: '新话题名字' }).fill('协作讨论');
  await capture(page, 'route-new-topic-390');
  await page.getByRole('button', { name: '确认本地归属' }).click();
  await expect(message).toContainText(original);
  await expect(message.getByRole('button', { name: /^归入：家庭 · 协作讨论/ })).toBeVisible();
  await page.reload();
  await expect(message.getByRole('button', { name: /^归入：事业学业 · 跳槽/ })).toBeVisible();
  await expect(message).toContainText(original);
  await open(page, 'chat?space=career&topic=interview');
  await message.getByRole('button', { name: /^归入：/ }).click();
  await choose(page, '主区', '家庭');
  await page.getByRole('button', { name: '确认本地归属' }).click();
  await expect(message).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '跳槽 · 面试', exact: true })).toBeFocused();
});

test('整理草稿改名后先确认再应用，撤销也需确认', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, 'organize');
  await card(page, '跳槽 · 面试').getByRole('button', { name: '改名', exact: true }).click();
  await saveName(page, '面试准备');
  await page.getByRole('button', { name: '应用整理', exact: true }).click();
  await capture(page, 'apply-confirm-1440');
  await page.getByRole('button', { name: '取消', exact: true }).click();
  await expect(page.getByRole('button', { name: '应用整理', exact: true })).toBeFocused();
  await page.getByRole('navigation', { name: '功能区预览页面' }).getByRole('link', { name: '区与话题' }).click();
  await expect(page.locator('[data-message="i2"]')).toContainText('归入：事业学业 · 跳槽 · 面试');
  await page.getByRole('navigation', { name: '功能区预览页面' }).getByRole('link', { name: '整理建议' }).click();
  await page.getByRole('button', { name: '应用整理', exact: true }).click();
  await page.getByRole('button', { name: '确认应用演示整理' }).click();
  await expect(page.getByText(/当前演示批次：/)).toContainText('demo-');
  await expect(page.getByRole('button', { name: '应用整理', exact: true })).toBeDisabled();
  await page.getByRole('navigation', { name: '功能区预览页面' }).getByRole('link', { name: '区与话题' }).click();
  await expect(page.locator('[data-message="i2"]')).toContainText('归入：事业学业 · 面试准备');
  await page.getByRole('navigation', { name: '功能区预览页面' }).getByRole('link', { name: '整理建议' }).click();
  await page.getByRole('button', { name: '撤销本批整理' }).click();
  await capture(page, 'revert-confirm-1440');
  await page.getByRole('button', { name: '取消', exact: true }).click();
  await expect(page.getByRole('button', { name: '撤销本批整理' })).toBeEnabled();
  await page.getByRole('button', { name: '撤销本批整理' }).click();
  await page.getByRole('button', { name: '确认撤销演示整理' }).click();
  await expect(card(page, '跳槽 · 面试')).toBeVisible();
  await expect(page.getByRole('button', { name: '撤销本批整理' })).toBeDisabled();
});

test('整理树支持合并、拆分、移动和忽略，消息总数不变', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, 'organize');
  await card(page, '跳槽 · 面试').getByRole('button', { name: '合并', exact: true }).click();
  await page.getByRole('button', { name: '保存到草稿' }).click();
  await expect(card(page, '学习计划')).toContainText('6 条消息');
  await expect(card(page, '跳槽 · 面试')).toHaveCount(0);
  await page.getByRole('button', { name: '重置草稿' }).click();
  await card(page, '跳槽 · 面试').getByRole('button', { name: '拆分', exact: true }).click();
  await page.getByRole('checkbox').nth(2).check();
  await page.getByRole('checkbox').nth(3).check();
  await page.getByRole('textbox', { name: '新话题名称' }).fill('协作练习');
  await capture(page, 'split-editor-390');
  await page.getByRole('button', { name: '保存到草稿' }).click();
  await expect(card(page, '协作练习')).toContainText('2 条消息');
  await expect(card(page, '跳槽 · 面试')).toContainText('2 条消息');
  await card(page, '协作练习').getByRole('button', { name: '移动', exact: true }).click();
  await choose(page, '移到哪个区', '家庭');
  await page.getByRole('button', { name: '保存到草稿' }).click();
  await expect(page.locator('.organize-space').filter({ has: page.getByText('家庭', { exact: true }) })).toContainText(
    '协作练习',
  );
  await card(page, '学习计划').getByRole('button', { name: '忽略本批' }).click();
  await expect(page.getByRole('region', { name: '本批忽略的话题' })).toContainText('学习计划');
  await expect(page.getByText(/原消息共 18 条/)).toBeVisible();
});

test('关于我按区列记忆、重要的人与事项，真实入口不会混入合成记录', async ({ page }) => {
  await open(page, 'me');
  await expect(page.getByRole('region', { name: /记忆分组$/ })).toHaveCount(7);
  await expect(page.getByRole('region', { name: '家庭记忆分组' })).toContainText('家人甲（合成人物）');
  await page.getByRole('link', { name: '准备产品岗位面试（合成事项）' }).click();
  await expect(page.locator('[data-message]')).toHaveCount(4);
  await page.getByRole('link', { name: '返回真实对话' }).click();
  await expect(page.getByRole('dialog', { name: '登录明镜台' })).toBeVisible();
  await expect(page.locator('[data-runtime="spaces-demo"]')).toHaveCount(0);
  expect(new URL(page.url()).searchParams.has('spaces')).toBe(false);
});
