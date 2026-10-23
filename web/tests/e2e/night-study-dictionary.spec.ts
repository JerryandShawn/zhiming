import { expect, test } from '@playwright/test';
import {
  assertStudyQuiet,
  auditStudy,
  captureStudy,
  choose,
  dictionary,
  insideDialog,
  openStudy,
  prepareStudy,
  rows,
  tab,
} from './night-study-helpers';

test.use({ timezoneId: 'Asia/Shanghai', serviceWorkers: 'allow' });
test.beforeEach(async ({ page }) => prepareStudy(page));
test.afterEach(({ page }) => assertStudyQuiet(page));

for (const width of [390, 1440]) {
  test(`研习词典：分页、别名、体系、来源与空结果 ${width}`, async ({ page }, info) => {
    await openStudy(page, width, width === 390 ? 'dark' : 'light');
    await tab(page, '术语词典');
    await expect(rows(page).getByRole('listitem')).toHaveCount(12);
    await expect(dictionary(page).getByRole('status')).toContainText('找到 212 条术语，先显示前12条');
    await dictionary(page).getByRole('button', { name: '再看12条', exact: true }).click();
    await expect(rows(page).getByRole('listitem')).toHaveCount(24);
    const search = dictionary(page).getByRole('searchbox', { name: '搜索术语', exact: true });
    await search.fill('日元');
    const term = rows(page).getByRole('button', { name: '查看术语：日主 八字 · 日元、日干', exact: true });
    await expect(term).toBeVisible();
    await expect(rows(page)).toContainText('日元、日干');
    await term.click();
    const detail = page.getByRole('dialog', { name: '日主 · 术语解释', exact: true });
    await expect(detail.locator('[data-term-id="bazi-day-master"]')).toHaveAttribute(
      'data-study-stage',
      'draft_complete_200_for_review',
    );
    for (const title of ['白话解释', '一个例句', '流派与适用范围', '仍待核对', '出处与支持范围'])
      await expect(detail.getByRole('heading', { name: title, exact: true })).toBeVisible();
    await expect(detail).toContainText('它是盘里的坐标，不是一个人的完整性格');
    await expect(detail).toContainText('支持日干作为十神参照的计算定义，不支持性格结论');
    await expect(detail).toContainText('子平十神坐标');
    await detail.getByText('词典版本与限制', { exact: true }).click();
    await expect(detail).toContainText('v1_ready_editorial_reviewed');
    await expect(detail).toContainText('具体原典版页仍以每条来源说明为准');
    await insideDialog(page, detail);
    await auditStudy(page);
    await captureStudy(page, `study-dictionary-alias-detail-${width}`, info);
    await page.keyboard.press('Escape');
    await expect(detail).toHaveCount(0);
    await expect(term).toBeFocused();
    await expect(search).toHaveValue('日元');
    await search.fill('');
    await choose(page, '术语体系', '塔罗');
    await expect(dictionary(page).getByRole('status')).toContainText('找到 35 条塔罗术语');
    await expect(rows(page).getByRole('listitem')).toHaveCount(12);
    const resultNames = await rows(page)
      .getByRole('button')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('aria-label')));
    expect(resultNames.every((name) => name !== null && / 塔罗(?: ·|$)/.test(name))).toBe(true);
    await search.fill('没有这个词条_合成边界_20261021');
    await expect(dictionary(page).getByRole('status')).toContainText('找到 0 条塔罗术语');
    await expect(rows(page)).toHaveCount(0);
    await expect(dictionary(page)).toContainText('不会临时编造释义');
    await auditStudy(page);
    await captureStudy(page, `study-dictionary-no-result-${width}`, info);
    await search.fill('日主');
    await choose(page, '术语体系', '八字');
    await expect(
      rows(page).getByRole('button', { name: '查看术语：日主 八字 · 日元、日干', exact: true }),
    ).toBeVisible();
  });
}
