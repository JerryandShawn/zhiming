import { expect, test } from '@playwright/test';
import { assertNightQuiet, auditNight, captureNight, guardNight, openNight } from './night-helpers';

test.beforeEach(({ page }) => guardNight(page));
test.afterEach(({ page }) => assertNightQuiet(page));

for (const theme of ['light', 'dark'])
  for (const width of [390, 1440]) {
    test(`对话卡布局、提问只读与审计 ${width} ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
      await openNight(page);
      await expect(page.locator('[data-complete="true"]')).toBeVisible();
      await expect(page.getByRole('region', { name: '待确认记忆' })).toBeVisible();
      const decisions = page.locator('.live-decision-options');
      expect(await decisions.locator('.decision-card').count()).toBe(2);
      if (width === 390) expect(await decisions.evaluate((node) => node.scrollWidth > node.clientWidth)).toBe(true);
      else {
        const boxes = await Promise.all(
          (await decisions.locator('.decision-card').all()).map((card) => card.boundingBox()),
        );
        expect(boxes[0]!.y).toBeCloseTo(boxes[1]!.y);
        expect(boxes[0]!.x).toBeLessThan(boxes[1]!.x);
      }
      const ask = page.getByRole('region', { name: '明镜的提问' });
      await decisions.scrollIntoViewIfNeeded();
      await captureNight(page, `01-decisions-${width}-${theme}`);
      await ask.getByRole('button', { name: '我自己说', exact: true }).click();
      await expect(page.getByRole('textbox', { name: '和明镜说说' })).toBeFocused();
      await ask.scrollIntoViewIfNeeded();
      await captureNight(page, `01-chat-cards-${width}-${theme}`);
      await auditNight(page);
      await ask.getByRole('button', { name: '先做个小试验', exact: true }).click();
      await expect(ask).toHaveAttribute('data-answer-state', 'answered');
      for (const button of await ask.getByRole('button').all()) await expect(button).toBeDisabled();
      await expect(ask.getByRole('button', { name: '先做个小试验', exact: true })).toHaveAttribute(
        'aria-pressed',
        'true',
      );
      await captureNight(page, `01-chat-answered-${width}-${theme}`);
    });
  }

test('记忆已保存可撤销，待确认记住后再撤销', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openNight(page);
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  await page.getByRole('button', { name: '撤销使用', exact: true }).click();
  await expect(page.getByText(/已撤销，不会再/)).toBeVisible();
  const pending = page.getByRole('region', { name: '待确认记忆' });
  await pending.scrollIntoViewIfNeeded();
  await captureNight(page, '01-memory-pending-390');
  await pending.getByRole('button', { name: '记住', exact: true }).click();
  await expect(pending).toHaveCount(0);
  await expect(page.getByRole('region', { name: '记忆记录' })).toContainText('已记下');
  await captureNight(page, '01-memory-saved-390');
  await page.getByRole('button', { name: '撤销使用', exact: true }).click();
  await expect(page.getByText(/已撤销，不会再/)).toHaveCount(2);
  await captureNight(page, '01-memory-undone-390');
});

for (const action of ['不用', '以后这类都记'])
  test(`待确认记忆：${action}`, async ({ page }) => {
    await openNight(page);
    await expect(page.locator('[data-complete="true"]')).toBeVisible();
    await page.getByRole('region', { name: '待确认记忆' }).getByRole('button', { name: action, exact: true }).click();
    await expect(page.getByRole('region', { name: '待确认记忆' })).toHaveCount(0);
    await expect(
      page.getByText(
        action === '不用' ? '这次不记，此条没有保存为有效记忆。' : '已记下这条信息，并更新了本地同类记忆偏好。',
        { exact: true },
      ),
    ).toBeVisible();
    await captureNight(page, action === '不用' ? '01-memory-dismissed-1440' : '01-memory-category-1440');
  });

test('复核标记、替换、恢复与中断重试', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openNight(page);
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  await page.getByRole('button', { name: '查看修订过程' }).click();
  await expect(page.getByText('复核中', { exact: true })).toBeVisible();
  await captureNight(page, '01-review-pending-1440');
  await expect(page.getByText('已修订', { exact: true })).toBeVisible();
  await expect(page.getByText(/第一版：/)).toHaveCount(0);
  await expect(page.getByText('复核中', { exact: true })).toHaveCount(0);
  await page.getByText('已修订', { exact: true }).focus();
  await expect(page.getByRole('tooltip')).toHaveText('复核后修正了一处说法');
  await captureNight(page, '01-review-replaced-1440');
  await page.getByRole('button', { name: '查看恢复片段' }).click();
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  await expect(page.getByText('已修订', { exact: true })).toHaveCount(0);
  await expect(page.getByText('旧片段', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '查看中断与重试' }).click();
  await expect(page.getByRole('alert')).toHaveText('这次演示中途停下了，可以重试这一轮。');
  await expect(page.locator('.tool-status.live')).toHaveCount(0);
  await captureNight(page, '01-interrupted-1440');
  await page.getByRole('button', { name: '重试这一轮演示' }).click();
  await expect(page.getByRole('alert')).toHaveText('这次演示中途停下了，可以重试这一轮。');
});

test('工具进行中可见，完成后收起详情', async ({ page }) => {
  await openNight(page);
  await page.getByRole('button', { name: '重放对话' }).click();
  await expect(page.locator('.tool-status.live')).toBeVisible();
  await captureNight(page, '01-tool-running-1440');
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  await expect(page.locator('.tool-status.live')).toHaveCount(0);
  const details = page.locator('.tool-progress details');
  await expect(details).not.toHaveAttribute('open');
  await details.locator('summary').click();
  await expect(details).toContainText('已完成');
  await captureNight(page, '01-tool-complete-1440');
});

test('离开再回对话开启新轮，自己的文字确认后只读', async ({ page }) => {
  await openNight(page);
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  const ask = page.getByRole('region', { name: '明镜的提问' });
  await ask.getByRole('button', { name: '先做个小试验', exact: true }).click();
  await expect(ask).toHaveAttribute('data-answer-state', 'answered');
  await page.evaluate(() => {
    location.hash = '/settings';
  });
  await expect(page.locator('[data-page="settings"]')).toBeVisible();
  await page.evaluate(() => {
    location.hash = '/chat';
  });
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  await ask.getByRole('button', { name: '我自己说', exact: true }).click();
  await page.getByRole('textbox', { name: '和明镜说说' }).fill('我想先听听第三种走法（合成试写）');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(ask).toHaveAttribute('data-answer-state', 'answered');
  await expect(ask).toContainText('你选了：我想先听听第三种走法（合成试写）');
});
