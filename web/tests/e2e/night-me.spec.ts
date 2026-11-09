import { expect, test, type Page } from '@playwright/test';
import { assertNightQuiet, auditNight, captureNight, guardNight, openNight } from './night-helpers';

const sections = [
  ['basic', '称呼与基本情况'],
  ['current_life', '现在的生活'],
  ['goals', '在意的事与目标'],
  ['people', '重要的人'],
  ['preferences', '偏好与禁忌'],
  ['communication', '沟通偏好'],
  ['chart_summary', '命理档案摘要'],
  ['followups', '正在跟进'],
] as const;
const me = (page: Page) => page.locator('[data-runtime="night-me"]');
const memory = (page: Page, id: string) => me(page).locator(`[data-memory-id="${id}"]`);
const profile = (page: Page, id: string) => me(page).locator(`[data-profile-id="profile-${id}"]`);
const proposal = (page: Page, id: string) => me(page).locator(`[data-proposal-id="${id}"]`);
const unauthorized = '这句未授权节选不应整段展示';

async function tab(page: Page, name: string) {
  await me(page).getByRole('group', { name: '关于我的分区' }).getByRole('button', { name, exact: true }).click();
}
async function route(page: Page, name: 'chat' | 'me') {
  await page.evaluate((value) => {
    location.hash = `/${value}`;
  }, name);
  await expect(page.locator(`[data-page="${name}"]`)).toBeVisible();
}
async function closePanel(page: Page) {
  await page.getByRole('dialog').getByRole('button', { name: '关闭', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
}
async function deletion(page: Page, id: string, scope: 'fact' | 'source') {
  await memory(page, id).getByRole('button', { name: '删除记忆', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '删除记忆', exact: true });
  await dialog.getByRole('radio', { name: scope === 'fact' ? /^只删这条/ : /^删除整段来源/ }).check();
  await dialog.getByRole('button', { name: '预览删除范围', exact: true }).click();
  return dialog;
}

test.beforeEach(({ page }) => guardNight(page));
test.afterEach(({ page }) => assertNightQuiet(page));

for (const theme of ['light', 'dark'])
  for (const width of [390, 1440]) {
    test(`关于我八节、记忆、提案与来源审计 ${width} ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
      await openNight(page, 'me');
      await expect(me(page)).toBeVisible();
      for (const [id, label] of sections) {
        await expect(me(page).getByRole('region', { name: label, exact: true })).toBeVisible();
        await expect(profile(page, id)).toBeVisible();
      }
      await expect(me(page).getByText('你改过', { exact: true })).toHaveCount(0);
      await auditNight(page);
      await captureNight(page, `03-me-profile-${width}-${theme}`, true);
      await tab(page, '记忆');
      await expect(me(page).locator('[data-memory-id]')).toHaveCount(8);
      await auditNight(page);
      await captureNight(page, `03-me-memories-${width}-${theme}`, true);
      await memory(page, 'memory-basic').getByRole('button', { name: '查看来源', exact: true }).click();
      const source = page.getByRole('dialog', { name: '来源原话', exact: true });
      await expect(source).toContainText('请叫我阿远，目前在学习产品设计。');
      await expect(page.locator('body')).not.toContainText(unauthorized);
      await auditNight(page);
      await captureNight(page, `03-me-source-${width}-${theme}`);
      await closePanel(page);
      await tab(page, '待确认');
      await expect(me(page).locator('[data-proposal-id]')).toHaveCount(3);
      await auditNight(page);
      await captureNight(page, `03-me-proposals-${width}-${theme}`, true);
    });
  }

for (const [id, label] of sections) {
  test(`画像条目查看、取消、确认编辑与删除：${label}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openNight(page, 'me');
    const item = profile(page, id);
    await expect(item).toBeVisible();
    const initialRevision = await me(page).getAttribute('data-revision');
    await item.getByRole('button', { name: `查看画像条目：${label}`, exact: true }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await closePanel(page);
    await expect(me(page)).toHaveAttribute('data-revision', initialRevision!);
    const edit = () => item.getByRole('button', { name: `编辑画像条目：${label}`, exact: true }).click();
    await edit();
    const editor = page.getByRole('dialog', { name: '修改画像条目', exact: true });
    const revised = `${label}：由我明确修改的合成条目。`;
    await editor.getByRole('textbox', { name: '你的说法', exact: true }).fill(revised);
    await expect(item.getByText('你改过', { exact: true })).toHaveCount(0);
    await closePanel(page);
    await expect(me(page)).toHaveAttribute('data-revision', initialRevision!);
    await expect(item).not.toContainText(revised);
    await edit();
    await editor.getByRole('textbox', { name: '你的说法', exact: true }).fill(revised);
    if (id === 'chart_summary') await expect(editor).toContainText('不会改变盘面或出生资料');
    await editor.getByRole('button', { name: '保存修改', exact: true }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(item).toContainText(revised);
    await expect(item.getByText('你改过', { exact: true })).toBeVisible();
    await expect(me(page)).toHaveAttribute('data-revision', String(Number(initialRevision) + 1));
    await captureNight(page, `03-profile-edited-${id}-390`);
    await item.getByRole('button', { name: `删除画像条目：${label}`, exact: true }).click();
    const confirmation = page.getByRole('dialog', { name: '删除画像条目', exact: true });
    await expect(confirmation).toBeVisible();
    const beforeDelete = await me(page).getAttribute('data-revision');
    await closePanel(page);
    await expect(item).toBeVisible();
    await expect(me(page)).toHaveAttribute('data-revision', beforeDelete!);
    await item.getByRole('button', { name: `删除画像条目：${label}`, exact: true }).click();
    await confirmation.getByRole('button', { name: '确认删除画像条目', exact: true }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(item).toHaveCount(0);
    await expect(me(page).getByRole('region', { name: label, exact: true })).toBeVisible();
    await expect(me(page)).toHaveAttribute('data-revision', String(Number(beforeDelete) + 1));
  });
}

for (const action of ['记住', '不用', '以后这类都记']) {
  test(`待确认内容在实际选择后才变化：${action}`, async ({ page }) => {
    await openNight(page, 'me');
    await tab(page, '记忆');
    await expect(me(page).locator('[data-memory-id]')).toHaveCount(8);
    await expect(me(page)).not.toContainText('希望跟进一项健康安排（合成示例）');
    await tab(page, '待确认');
    const pending = proposal(page, 'local-proposal');
    await expect(pending).toContainText('希望跟进一项健康安排（合成示例）');
    await expect(me(page)).toHaveAttribute('data-revision', '1');
    await pending.getByRole('button', { name: action, exact: true }).click();
    await expect(pending).toHaveCount(0);
    await expect(me(page)).toHaveAttribute('data-revision', '2');
    await tab(page, '记忆');
    await expect(me(page).locator('[data-memory-id]')).toHaveCount(action === '不用' ? 8 : 9);
    if (action === '不用') await expect(me(page)).not.toContainText('希望跟进一项健康安排（合成示例）');
    else await expect(me(page)).toContainText('希望跟进一项健康安排（合成示例）');
    await captureNight(
      page,
      `03-proposal-${action === '不用' ? 'dismissed' : action === '记住' ? 'saved' : 'category'}-1440`,
    );
  });
}

test('两种删除预览与取消均零mutation，删除单条保留整段原话和同源其他记录', async ({ page }) => {
  await openNight(page, 'me');
  await tab(page, '记忆');
  const before = await me(page).getAttribute('data-revision');
  for (const scope of ['fact', 'source'] as const) {
    await deletion(page, 'memory-basic', scope);
    await closePanel(page);
    await expect(me(page)).toHaveAttribute('data-revision', before!);
    await expect(me(page).locator('[data-memory-id]')).toHaveCount(8);
  }
  const dialog = await deletion(page, 'memory-basic', 'fact');
  await dialog.getByRole('button', { name: '确认删除这条', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(memory(page, 'memory-basic')).toHaveCount(0);
  await expect(memory(page, 'memory-life')).toBeVisible();
  await memory(page, 'memory-life').getByRole('button', { name: '查看来源', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '来源原话' })).toContainText('最近在准备产品岗位面试。');
  await expect(page.locator('body')).not.toContainText(unauthorized);
  await closePanel(page);
  await tab(page, '画像');
  await expect(profile(page, 'basic')).toHaveCount(0);
  await expect(profile(page, 'current_life')).toBeVisible();
  await tab(page, '待确认');
  await expect(proposal(page, 'local-proposal-career')).toBeVisible();
});

test('删除来源严格按messageId连带两条记忆、两条画像和一个提案', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openNight(page, 'me');
  await tab(page, '记忆');
  const dialog = await deletion(page, 'memory-basic', 'source');
  await captureNight(page, '03-delete-source-preview-390');
  await auditNight(page);
  await dialog.getByRole('button', { name: '确认删除整段来源', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(me(page)).toHaveAttribute('data-revision', '2');
  for (const id of ['memory-basic', 'memory-life']) await expect(memory(page, id)).toHaveCount(0);
  for (const id of [
    'memory-goals',
    'memory-people',
    'memory-boundaries',
    'local-preference',
    'memory-chart',
    'memory-followup',
  ])
    await expect(memory(page, id)).toBeVisible();
  await expect(me(page).locator('[data-memory-id]')).toHaveCount(6);
  await tab(page, '画像');
  await expect(profile(page, 'basic')).toHaveCount(0);
  await expect(profile(page, 'current_life')).toHaveCount(0);
  for (const [id] of sections.slice(2)) await expect(profile(page, id)).toBeVisible();
  await tab(page, '待确认');
  await expect(proposal(page, 'local-proposal-career')).toHaveCount(0);
  await expect(proposal(page, 'local-proposal')).toBeVisible();
  await expect(proposal(page, 'legacy-note')).toBeVisible();
  await captureNight(page, '03-delete-source-result-390');
});

test('Panel返回只关闭自身、回焦且前进不重开，取消保持版本', async ({ page }) => {
  await openNight(page, 'chat');
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  await route(page, 'me');
  const revision = await me(page).getAttribute('data-revision');
  const trigger = profile(page, 'basic').getByRole('button', { name: '编辑画像条目：称呼与基本情况', exact: true });
  await trigger.click();
  await page.getByRole('textbox', { name: '你的说法', exact: true }).fill('取消后不应保存的合成草稿');
  await page.goBack();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page).toHaveURL(/#\/me$/);
  await expect(trigger).toBeFocused();
  await expect(me(page)).toHaveAttribute('data-revision', revision!);
  await page.goForward();
  await expect(page).toHaveURL(/#\/me$/);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(me(page)).not.toContainText('取消后不应保存的合成草稿');
});

test('Chat撤销与Me共享记录，新版本在跨页及重放旧事件后不复活', async ({ page }) => {
  await openNight(page, 'chat');
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  await page.getByRole('button', { name: '撤销使用', exact: true }).click();
  await expect(page.getByText('已撤销，不会再提起', { exact: true })).toBeVisible();
  await route(page, 'me');
  await tab(page, '记忆');
  await expect(memory(page, 'local-preference')).toContainText(/停用|撤销/);
  await expect(me(page)).toHaveAttribute('data-revision', '2');
  await route(page, 'chat');
  await expect(page.getByText('已撤销，不会再提起', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '重放对话', exact: true }).click();
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  await expect(page.getByText('已撤销，不会再提起', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: '记忆记录', exact: true })).toHaveCount(0);
  await captureNight(page, '03-shared-receipt-withdrawn-1440');
});

test('Me停用同一条记忆会更新已存在的Chat回执，重放仍保留高版本', async ({ page }) => {
  await openNight(page, 'chat');
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  await expect(page.getByRole('region', { name: '记忆记录', exact: true })).toContainText('偏好先看简短结论');
  await route(page, 'me');
  await tab(page, '记忆');
  const item = memory(page, 'local-preference');
  await item.getByRole('button', { name: '停用记忆', exact: true }).click();
  await expect(item).toHaveAttribute('data-status', 'active');
  await expect(item).toHaveAttribute('data-revision', '1');
  await expect(me(page)).toHaveAttribute('data-revision', '1');
  await page
    .getByRole('dialog', { name: '停用记忆', exact: true })
    .getByRole('button', { name: '确认停用记忆', exact: true })
    .click();
  await expect(item).toHaveAttribute('data-status', 'stopped');
  await expect(item).toHaveAttribute('data-revision', '2');
  await route(page, 'chat');
  await expect(page.getByText('已撤销，不会再提起', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: '记忆记录', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '重放对话', exact: true }).click();
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  await expect(page.getByText('已撤销，不会再提起', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: '记忆记录', exact: true })).toHaveCount(0);
});

test('Chat确认提案在Me只生成一条有效记忆，旧提案事件不会重新要求确认', async ({ page }) => {
  await openNight(page, 'chat');
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  const pending = page.getByRole('region', { name: '待确认记忆', exact: true });
  await pending.getByRole('button', { name: '记住', exact: true }).click();
  await expect(pending).toHaveCount(0);
  await route(page, 'me');
  await tab(page, '记忆');
  const health = me(page).locator('[data-memory-id]').filter({ hasText: '希望跟进一项健康安排（合成示例）' });
  await expect(health).toHaveCount(1);
  await expect(health).toHaveAttribute('data-status', 'active');
  await expect(me(page).locator('[data-memory-id]')).toHaveCount(9);
  await tab(page, '待确认');
  await expect(proposal(page, 'local-proposal')).toHaveCount(0);
  await route(page, 'chat');
  await page.getByRole('button', { name: '重放对话', exact: true }).click();
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  await expect(pending).toHaveCount(0);
});

test('无痕内容不读取或改变共享画像记忆，退出恢复普通记录', async ({ page }) => {
  await openNight(page, 'chat');
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  await page.getByRole('switch', { name: '无痕模式', exact: true }).click();
  const privateChat = page.locator('[data-privacy="incognito"]');
  await expect(privateChat).toBeVisible();
  await expect(privateChat).not.toContainText('偏好先看简短结论');
  await expect(privateChat).not.toContainText('希望跟进一项健康安排');
  await privateChat.getByRole('textbox', { name: '和明镜说说', exact: true }).fill('PRIVATE_ME_ISOLATION_SYNTHETIC');
  await privateChat.getByRole('button', { name: '发送', exact: true }).click();
  await expect(privateChat.getByRole('button', { name: '停止回答' })).toHaveCount(0);
  await expect(privateChat.locator('.memory-receipt [aria-label="撤销使用"]')).toHaveCount(0);
  await page.getByRole('button', { name: '退出无痕', exact: true }).click();
  await route(page, 'me');
  await expect(me(page)).toHaveAttribute('data-revision', '1');
  await expect(me(page)).not.toContainText('PRIVATE_ME_ISOLATION_SYNTHETIC');
  await tab(page, '记忆');
  await expect(me(page).locator('[data-memory-id]')).toHaveCount(8);
  await tab(page, '待确认');
  await expect(me(page).locator('[data-proposal-id]')).toHaveCount(3);
});
