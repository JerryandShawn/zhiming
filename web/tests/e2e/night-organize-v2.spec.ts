import { expect, test, type Page } from '@playwright/test';
import { assertNightQuiet, auditNight, captureNight, guardNight } from './night-helpers';

test.use({ timezoneId: 'Asia/Shanghai' });
test.beforeEach(({ page }) => guardNight(page));
test.afterEach(({ page }) => assertNightQuiet(page));

const review = (page: Page) => page.locator('[data-runtime="organize-v2"]');
const topic = (page: Page, id: number) => review(page).locator(`[data-topic-id="proposal-${id}"]`);
const segment = (page: Page, id: number) => review(page).locator(`[data-segment-id="segment-${id}"]`);
async function openReview(page: Page, width = 1440, theme = 'light') {
  await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
  await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
  await page.goto('/?spaces=demo#/organize-review');
  await expect(page.getByRole('region', { name: '功能区模拟说明' })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await expect(review(page)).toHaveAttribute('data-state', 'draft');
}
async function accept(page: Page, id: number) {
  await segment(page, id).getByRole('button', { name: '接受', exact: true }).click();
  await expect(segment(page, id).getByText('已接受', { exact: true })).toBeVisible();
}
async function apply(page: Page) {
  await page.getByRole('button', { name: '应用已接受的整理', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '应用已接受的整理？', exact: true });
  await dialog.getByRole('button', { name: '确认应用', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(review(page)).toHaveAttribute('data-state', 'applied');
}
async function choose(page: Page, label: string, text: string) {
  await page.getByRole('combobox', { name: label, exact: true }).click();
  await page.getByRole('option', { name: text, exact: true }).click();
}

for (const theme of ['light', 'dark'])
  for (const width of [390, 1440]) {
    test(`旧对话审阅树与待整理区 ${width} ${theme}`, async ({ page }) => {
      await openReview(page, width, theme);
      await expect(page.getByRole('heading', { name: '旧对话审阅', exact: true })).toBeVisible();
      await expect(review(page).locator('[data-space-id]')).toHaveCount(7);
      await expect(review(page).locator('[data-topic-id]')).toHaveCount(8);
      await expect(review(page).locator('[data-segment-id]')).toHaveCount(8);
      await expect(page.getByRole('button', { name: '应用已接受的整理', exact: true })).toBeDisabled();
      await expect(topic(page, 2).getByRole('group', { name: '面试准备操作' }).getByRole('button')).toHaveCount(3);
      await expect(topic(page, 2).getByRole('button', { name: '合并话题', exact: true })).toHaveCount(0);
      await topic(page, 2).scrollIntoViewIfNeeded();
      await auditNight(page);
      await captureNight(page, `Q2-review-tree-${width}-${theme}`);
      const uncertain = page.getByRole('region', { name: '不确定，待你整理', exact: true });
      await expect(uncertain.locator('[data-segment-id="segment-1"]')).toHaveCount(1);
      await expect(topic(page, 1).locator('[data-segment-id]')).toHaveCount(0);
      await uncertain.scrollIntoViewIfNeeded();
      await auditNight(page);
      await captureNight(page, `Q2-review-uncertain-${width}-${theme}`);
    });
  }

test('改名取消零写、八十字边界与成功后只更新草稿', async ({ page }) => {
  await openReview(page, 390, 'dark');
  await topic(page, 2).getByRole('button', { name: '改名', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '修改话题名', exact: true });
  const input = dialog.getByRole('textbox', { name: '话题名', exact: true });
  await input.fill('取消的名字');
  await dialog.getByRole('button', { name: '取消', exact: true }).click();
  await expect(review(page)).toHaveAttribute('data-revision', '1');
  await expect(topic(page, 2).getByRole('heading', { name: '面试准备', exact: true })).toBeVisible();
  await topic(page, 2).getByRole('button', { name: '改名', exact: true }).click();
  await input.fill(' ');
  await expect(dialog.getByRole('button', { name: '保存到草稿', exact: true })).toBeDisabled();
  await input.fill('学'.repeat(81));
  await expect(input).toHaveAttribute('aria-invalid', 'true');
  await expect(dialog.getByRole('button', { name: '保存到草稿', exact: true })).toBeDisabled();
  await input.fill('面试练习');
  await auditNight(page);
  await captureNight(page, 'Q2-review-rename-390-dark');
  await dialog.getByRole('button', { name: '保存到草稿', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(topic(page, 2).getByRole('heading', { name: '面试练习', exact: true })).toBeVisible();
  await expect(review(page)).toHaveAttribute('data-revision', '2');
  await expect(review(page)).toHaveAttribute('data-state', 'draft');
  await expect(topic(page, 2).getByRole('button', { name: '改名', exact: true })).toBeFocused();
});

test('移动话题到别的区，保留片段与原话', async ({ page }) => {
  await openReview(page);
  await topic(page, 4)
    .getByRole('group', { name: '朋友相处操作', exact: true })
    .getByRole('button', { name: '移动', exact: true })
    .click();
  const dialog = page.getByRole('dialog', { name: '移动话题', exact: true });
  await choose(page, '目标区', '家庭');
  await auditNight(page);
  await captureNight(page, 'Q2-review-move-topic-1440-light');
  await dialog.getByRole('button', { name: '保存到草稿', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(review(page).locator('[data-space-id="family"] [data-topic-id="proposal-4"]')).toHaveCount(1);
  await expect(review(page).locator('[data-space-id="relationships"] [data-topic-id="proposal-4"]')).toHaveCount(0);
  await expect(segment(page, 4)).toContainText('和朋友约好一起看展，想先核对时间。');
  await expect(review(page)).toHaveAttribute('data-state', 'draft');
  await auditNight(page);
});

test('键盘更多菜单与同区合并，原触发器移除后焦点回标题', async ({ page }) => {
  await openReview(page, 390);
  const more = topic(page, 2).getByRole('button', { name: '更多', exact: true });
  await more.focus();
  await more.press('ArrowDown');
  const menu = page.getByRole('menu', { name: '面试准备更多操作', exact: true });
  await expect(menu.getByRole('menuitem', { name: '合并话题', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog', { name: '合并话题', exact: true });
  await expect(dialog.getByRole('combobox', { name: '并入哪个话题', exact: true })).toContainText('学习安排');
  await auditNight(page);
  await captureNight(page, 'Q2-review-merge-keyboard-390-light');
  await dialog.getByRole('button', { name: '保存到草稿', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(topic(page, 2)).toHaveCount(0);
  await expect(topic(page, 3).locator('[data-segment-id]')).toHaveCount(2);
  await expect(page.getByRole('heading', { name: '旧对话审阅', exact: true })).toBeFocused();
  await auditNight(page);
});

test('不确定片段移动后仍待确认，接受与拒绝互不串段', async ({ page }) => {
  await openReview(page, 390, 'dark');
  const uncertain = page.getByRole('region', { name: '不确定，待你整理', exact: true });
  await segment(page, 1).getByRole('button', { name: '移动', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '移动片段', exact: true });
  await choose(page, '目标区', '事业学业');
  await choose(page, '目标话题', '学习安排');
  await auditNight(page);
  await captureNight(page, 'Q2-review-move-segment-390-dark');
  await dialog.getByRole('button', { name: '保存到草稿', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(uncertain.locator('[data-segment-id="segment-1"]')).toContainText('建议话题：学习安排');
  await expect(uncertain.locator('[data-segment-id="segment-1"]')).toContainText('待审阅');
  await accept(page, 1);
  await expect(uncertain.locator('[data-segment-id]')).toHaveCount(0);
  await expect(topic(page, 3).locator('[data-segment-id="segment-1"]')).toHaveCount(1);
  await segment(page, 2).getByRole('button', { name: '拒绝', exact: true }).click();
  await expect(segment(page, 2)).toContainText('本批不整理');
  const summary = page.getByRole('region', { name: '应用前的变更摘要', exact: true });
  await expect(summary.locator('dl > div').filter({ has: page.getByText('已接受', { exact: true }) })).toContainText(
    '1 段',
  );
  await expect(summary.locator('dl > div').filter({ has: page.getByText('已拒绝', { exact: true }) })).toContainText(
    '1 段',
  );
  await summary.scrollIntoViewIfNeeded();
  await auditNight(page);
  await captureNight(page, 'Q2-review-before-summary-390-dark');
});

test('应用与整批撤销均需二次确认，取消保留原状态', async ({ page }) => {
  await openReview(page);
  await accept(page, 2);
  await page.getByRole('button', { name: '应用已接受的整理', exact: true }).click();
  let dialog = page.getByRole('dialog', { name: '应用已接受的整理？', exact: true });
  await expect(dialog).toContainText('15分钟内有效');
  await auditNight(page);
  await captureNight(page, 'Q2-review-apply-confirm-1440-light');
  await dialog.getByRole('button', { name: '取消', exact: true }).click();
  await expect(review(page)).toHaveAttribute('data-state', 'draft');
  await apply(page);
  await expect(page.getByRole('heading', { name: '已应用的变更', exact: true })).toBeVisible();
  await expect(segment(page, 2).getByRole('button', { name: '拒绝', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '撤销整批整理', exact: true }).click();
  dialog = page.getByRole('dialog', { name: '撤销这部分整理？', exact: true });
  await dialog.getByRole('button', { name: '取消', exact: true }).click();
  await expect(review(page)).toHaveAttribute('data-state', 'applied');
  await page.getByRole('button', { name: '撤销整批整理', exact: true }).click();
  await auditNight(page);
  await captureNight(page, 'Q2-review-revert-confirm-1440-light');
  await dialog.getByRole('button', { name: '确认撤销', exact: true }).click();
  await expect(review(page)).toHaveAttribute('data-state', 'reverted');
  await expect(segment(page, 2)).toContainText('想练习怎样把项目经过说清楚。');
  await auditNight(page);
});

test('只撤销所选标签字段，其他整理保留且随后能整批撤销', async ({ page }) => {
  await openReview(page, 390, 'dark');
  await accept(page, 2);
  await accept(page, 3);
  await apply(page);
  const checkbox = page.getByRole('checkbox', {
    name: '选择撤销：面试准备 · 片段2第1条 · 归区与话题标签',
    exact: true,
  });
  await checkbox.check();
  await page.getByRole('button', { name: '撤销所选字段', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '撤销这部分整理？', exact: true });
  await expect(dialog).toContainText('项关联字段');
  await auditNight(page);
  await captureNight(page, 'Q2-review-field-revert-390-dark');
  await dialog.getByRole('button', { name: '确认撤销', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(review(page)).toHaveAttribute('data-state', 'partially_reverted');
  await expect(checkbox).toHaveCount(0);
  await expect(
    page.getByRole('checkbox', { name: '选择撤销：学习安排 · 片段3第1条 · 归区与话题标签', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: '撤销整批整理', exact: true }).click();
  await dialog.getByRole('button', { name: '确认撤销', exact: true }).click();
  await expect(review(page)).toHaveAttribute('data-state', 'reverted');
  await auditNight(page);
});

test('应用确认超过十五分钟失效，重新确认才可应用', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-10-21T01:00:00+08:00') });
  await openReview(page);
  await accept(page, 2);
  await page.getByRole('button', { name: '应用已接受的整理', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '应用已接受的整理？', exact: true });
  await page.clock.fastForward(15 * 60 * 1000 + 1);
  await dialog.getByRole('button', { name: '确认应用', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('过期');
  await expect(review(page)).toHaveAttribute('data-state', 'draft');
  await auditNight(page);
  await captureNight(page, 'Q2-review-apply-expired-1440-light');
  await dialog.getByRole('button', { name: '重新确认', exact: true }).click();
  await dialog.getByRole('button', { name: '确认应用', exact: true }).click();
  await expect(review(page)).toHaveAttribute('data-state', 'applied');
});

test('撤销确认超过十五分钟失效，已应用标签保持不变', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-10-21T01:00:00+08:00') });
  await openReview(page, 390, 'dark');
  await accept(page, 2);
  await apply(page);
  await page.getByRole('button', { name: '撤销整批整理', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '撤销这部分整理？', exact: true });
  await page.clock.fastForward(15 * 60 * 1000 + 1);
  await dialog.getByRole('button', { name: '确认撤销', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('过期');
  await expect(review(page)).toHaveAttribute('data-state', 'applied');
  await auditNight(page);
  await captureNight(page, 'Q2-review-revert-expired-390-dark');
  await dialog.getByRole('button', { name: '取消', exact: true }).click();
  await expect(review(page)).toHaveAttribute('data-state', 'applied');
  await expect(page.getByRole('button', { name: '撤销整批整理', exact: true })).toBeFocused();
});

test('孤立撤销新话题先提示依赖，补选归属标签后可以完整撤销', async ({ page }) => {
  await openReview(page, 390, 'dark');
  await accept(page, 2);
  await apply(page);
  await page.getByRole('checkbox', { name: '选择撤销：面试准备 · 新建话题', exact: true }).check();
  await page.getByRole('button', { name: '撤销所选字段', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('status')).toContainText('请先同时选择该话题的归属标签');
  await expect(review(page)).toHaveAttribute('data-state', 'applied');
  await page.getByRole('checkbox', { name: '选择撤销：面试准备 · 片段2第1条 · 归区与话题标签', exact: true }).check();
  await auditNight(page);
  await captureNight(page, 'Q2-review-dependent-fields-390-dark');
  await page.getByRole('button', { name: '撤销所选字段', exact: true }).click();
  await page.getByRole('button', { name: '确认撤销', exact: true }).click();
  await expect(review(page)).toHaveAttribute('data-state', 'reverted');
});
