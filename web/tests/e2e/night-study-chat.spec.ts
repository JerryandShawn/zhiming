import { expect, test } from '@playwright/test';
import {
  assertStudyQuiet,
  auditStudy,
  captureStudy,
  composer,
  dictionary,
  insideDialog,
  openStudy,
  prepareStudy,
  rows,
  tab,
  tabTo,
  workspace,
} from './night-study-helpers';

test.use({ timezoneId: 'Asia/Shanghai', serviceWorkers: 'allow' });
test.beforeEach(async ({ page }) => prepareStudy(page));
test.afterEach(({ page }) => assertStudyQuiet(page));

for (const width of [390, 1440]) {
  test(`研习对话：原消息不改、键盘词义、切换保留草稿DOM ${width}`, async ({ page }, info) => {
    await openStudy(page, width, width === 390 ? 'dark' : 'light');
    const log = page.getByRole('log', { name: '合成消息时间线', exact: true });
    const messages = await log.allTextContents();
    expect(messages.join('')).toContain('命盘');
    await expect(log.getByRole('button', { name: /^查看术语：/ })).toHaveCount(0);
    const draft = '只在本地保留的研习问题\n切换词典和学习卡后继续写。';
    await composer(page).fill(draft);
    const initialUrl = page.url();
    const original = await composer(page).elementHandle();
    if (!original) throw new Error('Study composer is required');
    const hint = workspace(page).getByRole('complementary', { name: '研习提示合成示例', exact: true });
    const inline = hint.getByRole('button', { name: '查看术语：日主', exact: true });
    await expect(inline).toBeVisible();
    await tabTo(page, inline);
    await page.keyboard.press('Enter');
    const detail = page.getByRole('dialog', { name: '日主 · 术语解释', exact: true });
    await expect(detail).toBeVisible();
    await insideDialog(page, detail);
    await page.keyboard.press('Escape');
    await expect(detail).toHaveCount(0);
    await expect(inline).toBeFocused();
    await expect(page).toHaveURL(initialUrl);
    await tab(page, '术语词典');
    await dictionary(page).getByRole('searchbox', { name: '搜索术语', exact: true }).fill('上升点');
    await expect(rows(page).getByRole('button', { name: '查看术语：上升点 西方占星', exact: true })).toBeVisible();
    await tab(page, '学习卡');
    await expect(page.locator('[data-learning-sample="ayuan-bazi"] [data-learning-point]')).toHaveCount(11);
    await tab(page, '对话');
    await expect(composer(page)).toHaveValue(draft);
    expect(await original.evaluate((node) => node.isConnected)).toBe(true);
    expect(await original.evaluate((node) => node === document.getElementById('spaces-preview-draft'))).toBe(true);
    expect(await log.allTextContents()).toEqual(messages);
    await composer(page).press('End');
    await composer(page).press('Enter');
    await expect(composer(page)).toHaveValue(draft + '\n');
    await expect(workspace(page).getByRole('button', { name: '发送', exact: true })).toBeDisabled();
    await tab(page, '术语词典');
    await expect(dictionary(page).getByRole('searchbox', { name: '搜索术语', exact: true })).toHaveValue('上升点');
    await tab(page, '对话');
    await auditStudy(page);
    await captureStudy(page, `study-chat-retained-${width}`, info);
    await original.dispose();
  });
}
