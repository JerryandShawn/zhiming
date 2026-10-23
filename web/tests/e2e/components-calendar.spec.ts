import { test, expect } from '@playwright/test';
import { assertDemoQuiet, captureComponent, guardDemo, openDemo } from './components-helpers';

test.beforeEach(({ page }) => guardDemo(page));
test.afterEach(({ page }) => assertDemoQuiet(page));

test('桌面今日月历分别呈现休、班、节气、节日与安排，标记可读不只靠颜色', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openDemo(page, 'today');
  const calendar = page.getByRole('region', { name: '2026年10月日历' });
  await expect(calendar).toBeVisible();
  await expect(calendar.locator('[data-date="2026-10-01"]')).toHaveAccessibleName(/法定假日/);
  await expect(calendar.locator('[data-date="2026-10-10"]')).toHaveAccessibleName(/调休上班/);
  await expect(calendar.locator('[data-date="2026-10-08"]')).toHaveAccessibleName(/寒露/);
  await expect(calendar.locator('[data-date="2026-10-18"]')).toHaveAccessibleName(/重阳/);
  await expect(calendar.locator('[data-date="2026-10-21"]')).toHaveAccessibleName(/安排.*面试/);
  await expect(calendar.locator('[data-date="2026-10-17"]')).toHaveAttribute('aria-current', 'date');
  const marks = await calendar.evaluate((element) => {
    const style = (selector: string) => getComputedStyle(element.querySelector(selector)!);
    return {
      event: style('.calendar-event').backgroundColor,
      term: style('.calendar-term').backgroundColor,
      eventSize: style('.calendar-event').width,
      termSize: style('.calendar-term').width,
      columns: style('.calendar-grid').gridTemplateColumns.split(' ').length,
    };
  });
  expect(marks.columns).toBe(7);
  expect(marks.event).not.toBe(marks.term);
  expect(marks.eventSize).toBe('4px');
  expect(marks.termSize).toBe('4px');
  await captureComponent(page, 'calendar-five-markers-1440');
});

test('手机可打开月历抽屉，换月不会沿用示例标记，关闭回到入口', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await openDemo(page, 'today');
  const trigger = page.getByRole('button', { name: '查看本月日历', exact: true });
  await trigger.click();
  const dialog = page.getByRole('dialog', { name: '本月日历', exact: true });
  await expect(dialog.getByRole('region', { name: '2026年10月日历' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await captureComponent(page, 'calendar-mobile-sheet-375');
  await dialog.getByRole('button', { name: '下个月' }).click();
  const november = dialog.getByRole('region', { name: '2026年11月日历' });
  await expect(november).toBeVisible();
  await expect(november.locator('.calendar-mark, .calendar-festival, .calendar-term, .calendar-event')).toHaveCount(0);
  await expect(november).toContainText(/未加载|未知|未接入|未载入/);
  await dialog.getByRole('button', { name: '下个月' }).click();
  await dialog.getByRole('button', { name: '下个月' }).click();
  await expect(dialog.getByRole('region', { name: '2027年1月日历' })).toContainText('该年放假安排尚未公布');
  await captureComponent(page, 'calendar-unpublished-375');
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
});
