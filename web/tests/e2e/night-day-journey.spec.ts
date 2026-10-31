import { expect, test } from '@playwright/test';
import {
  assertDayJourneyQuiet,
  chat,
  composer,
  contact,
  dayCheckpoint,
  followup,
  healthMemory,
  healthReceipt,
  healthText,
  me,
  meTab,
  morning,
  navigateDayJourney,
  prepareDayJourney,
  revealDayReceipts,
  setBeijingClock,
  settings,
  today,
} from './night-day-journey-helpers';

test.use({ timezoneId: 'Asia/Shanghai', serviceWorkers: 'allow' });
test.beforeEach(async ({ page }) => prepareDayJourney(page));
test.afterEach(({ page }) => assertDayJourneyQuiet(page));

for (const [width, theme] of [
  [390, 'dark'],
  [1440, 'light'],
] as const) {
  test(`一天的使用：同页晨报、对话回执、跟进设置与晚上 ${width} ${theme}`, async ({ page }, info) => {
    test.setTimeout(180000);
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
    await page.goto('/?night=demo#/today'); // The only navigation creating a document in this test.
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    const document = await page.locator('html').elementHandle();
    if (!document) throw new Error('The day journey needs one live document');
    await expect(today(page)).toHaveAttribute('data-today', '2026-10-21');
    await expect(today(page)).toHaveAttribute('data-load-state', 'ready');
    await expect(
      today(page).locator('.today-clock').getByRole('heading', { name: '08:00', exact: true }),
    ).toBeVisible();
    await expect(today(page).locator('[data-daily-system]')).toHaveCount(3);
    await expect(today(page).locator('[data-plan-id="demo-reminder-today"]')).toHaveAttribute(
      'data-placement',
      'scheduled',
    );
    await expect(followup(page)).toHaveAttribute('data-placement', 'scheduled');
    await expect(today(page).locator('[data-plan-id="demo-reminder-overdue"]')).toHaveAttribute(
      'data-placement',
      'inbox-only',
    );
    await dayCheckpoint(page, `day-08-morning-${width}-${theme}`, info, { viewport: true });

    await today(page).getByRole('link', { name: '和明镜聊聊', exact: true }).click();
    await expect(chat(page)).toHaveAttribute('data-complete', 'true');
    const ask = chat(page).getByRole('region', { name: '明镜的提问', exact: true });
    const pending = chat(page).getByRole('region', { name: '待确认记忆', exact: true });
    await expect(pending).toContainText(healthText);
    await expect(pending).toContainText('尚未保存为有效记忆');
    await pending.scrollIntoViewIfNeeded();
    await dayCheckpoint(page, `day-08-chat-pending-${width}-${theme}`, info);
    await ask.getByRole('button', { name: '先做个小试验', exact: true }).click();
    await expect(ask).toHaveAttribute('data-answer-state', 'answered');
    await expect(ask).toContainText('先做个小试验');
    const draft = '今晚回来继续想这个问题（合成草稿，尚未提交）。';
    await composer(page).fill(draft);
    await pending.getByRole('button', { name: '记住', exact: true }).click();
    await expect(pending).toHaveCount(0);
    await revealDayReceipts(page);
    await expect(healthReceipt(page)).toContainText('已记下');
    await healthReceipt(page).scrollIntoViewIfNeeded();
    await dayCheckpoint(page, `day-08-memory-saved-${width}-${theme}`, info);

    // Move the clock while leaving Today unmounted; remount reads now through its actual lifecycle.
    await setBeijingClock(page, '12:00');
    await navigateDayJourney(page, width, '关于我');
    await expect(me(page)).toHaveAttribute('data-revision', '2');
    await meTab(page, '记忆');
    await expect(me(page).locator('[data-memory-id]')).toHaveCount(9);
    await expect(healthMemory(page)).toHaveAttribute('data-status', 'active');
    await expect(healthMemory(page)).toHaveAttribute('data-revision', '2');
    await healthMemory(page).scrollIntoViewIfNeeded();
    await dayCheckpoint(page, `day-12-shared-memory-${width}-${theme}`, info);
    await meTab(page, '待确认');
    await expect(me(page).locator('[data-proposal-id="local-proposal"]')).toHaveCount(0);
    await expect(me(page).locator('[data-proposal-id]')).toHaveCount(2);
    await me(page).getByRole('link', { name: '设置', exact: true }).click();
    await expect(settings(page)).toHaveAttribute('data-revision', '1');

    const morningTime = morning(page).getByLabel('晨报发送时间', { exact: true });
    await morningTime.fill('09:10');
    await expect(morning(page)).toHaveAttribute('data-revision', '1');
    await morning(page).getByRole('button', { name: '取消修改', exact: true }).click();
    await expect(morningTime).toHaveValue('07:00');
    await expect(morning(page)).toHaveAttribute('data-revision', '1');
    await expect(settings(page)).toHaveAttribute('data-revision', '1');
    await morning(page).scrollIntoViewIfNeeded();
    await dayCheckpoint(page, `day-12-report-cancelled-${width}-${theme}`, info);
    await morningTime.fill('07:30');
    await morning(page).getByRole('button', { name: '保存晨报设置', exact: true }).click();
    await expect(morning(page)).toHaveAttribute('data-revision', '2');
    await expect(morning(page).getByRole('status')).toContainText('已保存晨报设置');
    await expect(settings(page)).toHaveAttribute('data-revision', '2');
    await contact(page).getByRole('switch', { name: '跟进开关', exact: true }).click();
    await expect(contact(page).getByRole('switch', { name: '跟进开关', exact: true })).not.toBeChecked();
    await expect(settings(page)).toHaveAttribute('data-revision', '2');
    await contact(page).getByRole('button', { name: '保存主动联系设置', exact: true }).click();
    await expect(contact(page).getByRole('status')).toContainText('已保存主动联系设置');
    await expect(settings(page)).toHaveAttribute('data-revision', '3');
    await contact(page).scrollIntoViewIfNeeded();
    await dayCheckpoint(page, `day-12-contact-saved-${width}-${theme}`, info);
    await navigateDayJourney(page, width, '今日');
    await expect(today(page)).toHaveAttribute('data-load-state', 'ready');
    await expect(
      today(page).locator('.today-clock').getByRole('heading', { name: '12:00', exact: true }),
    ).toBeVisible();
    await expect(followup(page)).toHaveAttribute('data-placement', 'paused');
    await expect(followup(page)).toContainText('主动跟进已关闭');
    await expect(today(page).getByRole('region', { name: '晨报与联系', exact: true })).toContainText('07:30');
    await dayCheckpoint(page, `day-12-followup-paused-${width}-${theme}`, info, { viewport: true });

    await navigateDayJourney(page, width, '对话');
    await expect(chat(page)).toHaveAttribute('data-complete', 'true');
    await expect(ask).toHaveAttribute('data-answer-state', 'answered');
    await expect(composer(page)).toHaveValue(draft);
    await revealDayReceipts(page);
    await expect(healthReceipt(page)).toContainText('已记下');
    await setBeijingClock(page, '22:00');
    await healthReceipt(page).getByRole('button', { name: '撤销使用', exact: true }).click();
    await expect(healthReceipt(page)).toHaveCount(0);
    await expect(chat(page).getByText('已撤销，不会再提起', { exact: true })).toHaveCount(1);
    await chat(page).getByText('已撤销，不会再提起', { exact: true }).scrollIntoViewIfNeeded();
    await dayCheckpoint(page, `day-22-memory-revoked-${width}-${theme}`, info);
    await navigateDayJourney(page, width, '关于我');
    await expect(me(page)).toHaveAttribute('data-revision', '3');
    await meTab(page, '记忆');
    await expect(healthMemory(page)).toHaveAttribute('data-status', 'stopped');
    await expect(healthMemory(page)).toHaveAttribute('data-revision', '3');
    await expect(healthMemory(page)).toContainText('已停用，不会再提起');
    await expect(me(page).locator('[data-memory-id]')).toHaveCount(9); // Undo stops use; it does not delete the source.
    await me(page).getByRole('link', { name: '设置', exact: true }).click();
    await expect(settings(page)).toHaveAttribute('data-revision', '3');
    await expect(morningTime).toHaveValue('07:30');
    await expect(morning(page)).toHaveAttribute('data-revision', '2');
    await expect(contact(page).getByRole('switch', { name: '跟进开关', exact: true })).not.toBeChecked();
    await expect(contact(page).getByLabel('免打扰开始时间', { exact: true })).toHaveValue('22:00');
    await expect(contact(page).getByLabel('免打扰结束时间', { exact: true })).toHaveValue('08:00');
    await contact(page).getByRole('switch', { name: '跟进开关', exact: true }).click();
    await contact(page).getByRole('button', { name: '保存主动联系设置', exact: true }).click();
    await expect(settings(page)).toHaveAttribute('data-revision', '4');
    await expect(contact(page).getByRole('status')).toContainText('已保存主动联系设置');
    await contact(page).scrollIntoViewIfNeeded();
    await dayCheckpoint(page, `day-22-contact-restored-${width}-${theme}`, info);
    await navigateDayJourney(page, width, '今日');
    await expect(today(page)).toHaveAttribute('data-load-state', 'ready');
    await expect(today(page)).toHaveAttribute('data-today', '2026-10-21');
    await expect(
      today(page).locator('.today-clock').getByRole('heading', { name: '22:00', exact: true }),
    ).toBeVisible();
    await expect(followup(page)).toHaveAttribute('data-placement', 'quiet-hold');
    await expect(followup(page)).toContainText('免打扰中');
    await expect(today(page).locator('[data-plan-id="demo-reminder-today"]')).toHaveAttribute(
      'data-placement',
      'inbox-only',
    );
    await expect(today(page).getByRole('region', { name: '晨报与联系', exact: true })).toContainText('07:30');
    await dayCheckpoint(page, `day-22-followup-quiet-${width}-${theme}`, info, { viewport: true });
    await navigateDayJourney(page, width, '对话');
    await expect(chat(page)).toHaveAttribute('data-complete', 'true');
    await expect(ask).toHaveAttribute('data-answer-state', 'answered');
    await expect(composer(page)).toHaveValue(draft);
    await expect(chat(page).getByText('已撤销，不会再提起', { exact: true })).toHaveCount(1);
    await expect(chat(page).getByRole('region', { name: '待确认记忆', exact: true })).toHaveCount(0);
    await composer(page).scrollIntoViewIfNeeded();
    await dayCheckpoint(page, `day-22-chat-retained-${width}-${theme}`, info);
    expect(await document.evaluate((node) => node.isConnected)).toBe(true);
    await document.dispose();
    assertDayJourneyQuiet(page);
  });
}
