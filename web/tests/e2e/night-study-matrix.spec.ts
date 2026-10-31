import { expect, test } from '@playwright/test';
import {
  assertStudyQuiet,
  auditStudy,
  captureStudy,
  dictionary,
  learning,
  openStudy,
  prepareStudy,
  rows,
  tab,
  workspace,
} from './night-study-helpers';

test.use({ timezoneId: 'Asia/Shanghai', serviceWorkers: 'allow' });
test.beforeEach(async ({ page }) => prepareStudy(page));
test.afterEach(({ page }) => assertStudyQuiet(page));

for (const width of [375, 390, 768, 1440]) {
  for (const theme of ['light', 'dark']) {
    test(`研习视觉矩阵：对话/词典/卡/解释/依据 ${width} ${theme}`, async ({ page }, info) => {
      test.setTimeout(120000);
      await openStudy(page, width, theme);
      await auditStudy(page);
      await captureStudy(page, `study-matrix-chat-${width}-${theme}`, info);
      const inline = workspace(page)
        .getByRole('complementary', { name: '研习提示合成示例', exact: true })
        .getByRole('button', { name: '查看术语：日主', exact: true });
      await inline.click();
      const detail = page.getByRole('dialog', { name: '日主 · 术语解释', exact: true });
      await expect(detail.locator('[data-term-id="bazi-day-master"]')).toBeVisible();
      await auditStudy(page);
      await captureStudy(page, `study-matrix-detail-${width}-${theme}`, info);
      await page.keyboard.press('Escape');
      await expect(detail).toHaveCount(0);
      await expect(inline).toBeFocused();
      await tab(page, '术语词典');
      await expect(rows(page).getByRole('listitem')).toHaveCount(12);
      await expect(dictionary(page)).toContainText('共212条术语、39处登记出处');
      await auditStudy(page);
      await captureStudy(page, `study-matrix-dictionary-${width}-${theme}`, info);
      await tab(page, '学习卡');
      const sample = learning(page).locator('[data-learning-sample="ayuan-bazi"]');
      await expect(sample.locator('[data-learning-point]')).toHaveCount(11);
      await auditStudy(page);
      await captureStudy(page, `study-matrix-cards-${width}-${theme}`, info);
      const trigger = sample
        .locator('[data-learning-point="learning-2"]')
        .getByRole('button', { name: '依据〔r1〕', exact: true });
      await trigger.click();
      const evidence = page.getByRole('dialog', { name: '本学习样例依据〔r1〕', exact: true });
      await expect(evidence).toContainText('不等于格局成立');
      await auditStudy(page);
      await captureStudy(page, `study-matrix-evidence-${width}-${theme}`, info);
      await page.keyboard.press('Escape');
      await expect(evidence).toHaveCount(0);
      await expect(trigger).toBeFocused();
    });
  }
}
