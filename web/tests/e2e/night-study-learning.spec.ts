import { expect, test } from '@playwright/test';
import {
  assertStudyQuiet,
  auditStudy,
  captureStudy,
  choose,
  insideDialog,
  learning,
  openStudy,
  prepareStudy,
  tab,
} from './night-study-helpers';

test.use({ timezoneId: 'Asia/Shanghai', serviceWorkers: 'allow' });
test.beforeEach(async ({ page }) => prepareStudy(page));
test.afterEach(({ page }) => assertStudyQuiet(page));

for (const width of [390, 1440]) {
  test(`研习学习卡：三合成样例、同名r1隔离、返回回焦 ${width}`, async ({ page }, info) => {
    await openStudy(page, width, width === 390 ? 'dark' : 'light');
    await tab(page, '学习卡');
    const bazi = learning(page).locator('[data-learning-sample="ayuan-bazi"]');
    await expect(bazi.locator('[data-learning-point]')).toHaveCount(11);
    await expect(bazi).toContainText('先找日主');
    const rule = bazi
      .locator('[data-learning-point="learning-2"]')
      .getByRole('button', { name: '依据〔r1〕', exact: true });
    await rule.click();
    const dialog = page.getByRole('dialog', { name: '本学习样例依据〔r1〕', exact: true });
    await expect(dialog).toContainText('已核对的一项原生候选条件；不等于格局成立');
    await expect(dialog).toContainText('子平 · 项目候选条件实现');
    await expect(dialog.getByRole('heading', { name: '输入依据〔c12〕', exact: true })).toBeVisible();
    await expect(dialog).toContainText('第41章专论');
    await insideDialog(page, dialog);
    await auditStudy(page);
    await captureStudy(page, `study-learning-bazi-rule-${width}`, info);
    const url = page.url();
    await page.goBack();
    await expect(dialog).toHaveCount(0);
    await expect(page).toHaveURL(url);
    await expect(rule).toBeFocused();
    await choose(page, '学习卡体系', '紫微斗数 · 2张');
    const ziwei = learning(page).locator('[data-learning-sample="ayuan-ziwei"]');
    await expect(ziwei.locator('[data-learning-point]')).toHaveCount(2);
    await expect(bazi).toHaveCount(0);
    await expect(page.getByRole('dialog')).toHaveCount(0);
    const boundary = ziwei
      .locator('[data-learning-point="learning-2"]')
      .getByRole('button', { name: '依据〔r1〕', exact: true });
    await boundary.click();
    await expect(dialog).toContainText('已核对的交界条件；不据此倒推出生时辰');
    await expect(dialog).not.toContainText('子平 · 项目候选条件实现');
    await expect(dialog.getByRole('heading', { name: '输入依据〔c12〕', exact: true })).toHaveCount(0);
    for (const alias of ['c7', 'c8', 'c9'])
      await expect(dialog.getByRole('heading', { name: `输入依据〔${alias}〕`, exact: true })).toBeVisible();
    await auditStudy(page);
    await captureStudy(page, `study-learning-ziwei-boundary-${width}`, info);
    await dialog.getByRole('button', { name: '关闭', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(boundary).toBeFocused();
    await choose(page, '学习卡体系', '西方占星 · 2张');
    const astro = learning(page).locator('[data-learning-sample="ayuan-astro"]');
    await expect(astro.locator('[data-learning-point]')).toHaveCount(2);
    await expect(ziwei).toHaveCount(0);
    await expect(astro).toContainText('先读计算位置');
    const coordinates = astro
      .locator('[data-learning-point="learning-1"]')
      .getByRole('button', { name: '依据〔c2〕', exact: true });
    await coordinates.click();
    const utc = page.getByRole('dialog', { name: '本学习样例依据〔c2〕', exact: true });
    await expect(utc).toContainText('依据口径：实际时刻坐标');
    await page.keyboard.press('Escape');
    await expect(utc).toHaveCount(0);
    await expect(coordinates).toBeFocused();
    await choose(page, '学习卡体系', '八字 · 11张');
    await expect(bazi.locator('[data-learning-point]')).toHaveCount(11);
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(learning(page)).toContainText('不会把浏览记录写入记忆、档案或设备存储');
  });
}
