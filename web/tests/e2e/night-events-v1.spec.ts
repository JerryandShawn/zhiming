import { expect, test } from '@playwright/test';
import { assertNightQuiet, auditNight, captureNight, guardNight, openNight } from './night-helpers';

test.use({ timezoneId: 'Asia/Shanghai' });
test.beforeEach(({ page }) => guardNight(page));
test.afterEach(({ page }) => assertNightQuiet(page));

for (const theme of ['light', 'dark'])
  for (const width of [390, 1440]) {
    test(`冻结v1卡片：稳定选择、未知项、记忆确认 ${width} ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
      await openNight(page);
      const conversation = page.locator('[data-page="chat"][data-scenario="cards"]');
      await expect(conversation).toHaveAttribute('data-complete', 'true');

      const decisions = page.getByRole('region', { name: '可比较的选择', exact: true });
      await expect(decisions.locator('.decision-card')).toHaveCount(2);
      const trial = decisions.locator('[data-option-id="trial"]');
      const clarify = decisions.locator('[data-option-id="clarify"]');
      await expect(trial.getByRole('heading', { name: '先做一周小试验', exact: true })).toBeVisible();
      await expect(trial).toContainText('容易调整');
      await expect(clarify).toContainText('部分可调整');
      await expect(clarify.getByText('待确认', { exact: true })).toHaveCount(2);
      await expect(clarify.getByLabel('待确认事项', { exact: true })).toContainText('风险');
      await expect(decisions.getByText('easy', { exact: true })).toHaveCount(0);
      await decisions.scrollIntoViewIfNeeded();
      await auditNight(page);
      await captureNight(page, `Q1-v1-cards-${width}-${theme}`);

      const pending = page.getByRole('region', { name: '待确认记忆', exact: true });
      await expect(pending).toContainText('待你确认，尚未保存为有效记忆');
      const remember = pending.getByRole('button', { name: '记住', exact: true });
      await expect(remember).toBeEnabled();
      await remember.click();
      await expect(pending).toHaveCount(0);
      await expect(page.getByRole('status').filter({ hasText: '已记下这条信息。' })).toBeVisible();

      const ask = page.getByRole('region', { name: '明镜的提问', exact: true });
      await expect(ask).toHaveAttribute('data-ask-id', 'local-ask');
      const selected = ask.getByRole('button', { name: '先做个小试验', exact: true });
      await expect(selected).toHaveAttribute('data-option-id', 'trial');
      await selected.click();
      await expect(ask).toHaveAttribute('data-answer-state', 'answered');
      await expect(selected).toHaveAttribute('aria-pressed', 'true');
      await expect(ask).toContainText('你选了：先做个小试验');
      for (const button of await ask.getByRole('button').all()) await expect(button).toBeDisabled();
      await ask.scrollIntoViewIfNeeded();
      await auditNight(page);
      await captureNight(page, `Q1-v1-confirmed-${width}-${theme}`);
    });
  }

test('冻结v1 review：真实待复核状态结束后只保留修订正文与标记', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openNight(page);
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  await page.getByRole('button', { name: '查看修订过程', exact: true }).click();
  await expect(page.getByText('复核中', { exact: true })).toBeVisible();
  await expect(page.getByText('第一版：现在就把所有安排定下来。', { exact: true })).toBeVisible();
  await captureNight(page, 'Q1-v1-review-pending-1440');
  await expect(page.getByText('已修订', { exact: true })).toBeVisible();
  const conversation = page.locator('[data-scenario="review"]');
  await expect(conversation).toHaveAttribute('data-complete', 'true');
  await expect(page.getByText('复核中', { exact: true })).toHaveCount(0);
  await expect(page.getByText(/第一版：/)).toHaveCount(0);
  await expect(page.getByText(/先把选择缩小到一个可验证的小步骤/)).toBeVisible();
  await page.getByText('已修订', { exact: true }).focus();
  await expect(page.getByRole('tooltip')).toHaveText('复核后修正了一处说法');
  await page.keyboard.press('Escape');
  await auditNight(page);
  await captureNight(page, 'Q1-v1-review-revised-1440');
});

test('冻结v1 resumed：权威恢复替换正文，不把恢复误标成修订', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => localStorage.setItem('mingjing-theme', 'dark'));
  await openNight(page);
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  await page.getByRole('button', { name: '查看恢复片段', exact: true }).click();
  await expect(page.getByText('从已确认的片段继续，原来的重复文字已替换。', { exact: true })).toBeVisible();
  await expect(page.locator('[data-scenario="resumed"]')).toHaveAttribute('data-complete', 'true');
  await expect(page.getByText('旧片段', { exact: true })).toHaveCount(0);
  await expect(page.getByText(/先把选择缩小到一个可验证的小步骤/)).toHaveCount(0);
  await expect(page.getByText('已修订', { exact: true })).toHaveCount(0);
  await expect(page.getByText('复核中', { exact: true })).toHaveCount(0);
  await auditNight(page);
  await captureNight(page, 'Q1-v1-resumed-390-dark');
});
