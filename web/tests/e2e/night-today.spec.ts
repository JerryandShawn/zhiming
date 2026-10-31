import { expect, test, type Page } from '@playwright/test';
import { assertNightQuiet, auditNight, captureNight, guardNight, openNight } from './night-helpers';

test.use({ timezoneId: 'Asia/Shanghai' });
test.beforeEach(({ page }) => guardNight(page));
test.afterEach(({ page }) => assertNightQuiet(page));

const today = (page: Page) => page.locator('[data-runtime="night-today"]');
const selection = (page: Page) => page.getByLabel('查看哪天的流日', { exact: true });
async function openToday(page: Page, width = 1440, theme = 'light', clock = '2026-10-21T07:15:00+08:00') {
  await page.clock.setFixedTime(new Date(clock));
  await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
  await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
  await openNight(page, 'today');
  await expect(today(page)).toHaveAttribute('data-load-state', 'ready');
  await expect(today(page)).toHaveAttribute('data-today', '2026-10-21');
}

for (const theme of ['light', 'dark'])
  for (const width of [390, 1440]) {
    test(`晨报日期、公开流日和到期安排 ${width} ${theme}`, async ({ page }) => {
      await openToday(page, width, theme);
      await expect(today(page).getByRole('heading', { name: /10月21日.*星期三/ })).toBeVisible();
      await expect(today(page)).toContainText('节假日、调休、农历及节气资料尚未载入');
      await expect(today(page)).toContainText('合成引擎样例');
      await expect(today(page)).toContainText('真太阳时');
      await expect(today(page).locator('[data-daily-system]')).toHaveCount(3);
      await expect(
        today(page).getByRole('list', { name: '安排与提醒列表', exact: true }).getByRole('listitem'),
      ).toHaveCount(3);
      await expect(today(page).locator('[data-plan-id="demo-reminder-today"]')).toHaveAttribute(
        'data-placement',
        'scheduled',
      );
      const expired = today(page).locator('[data-plan-id="demo-reminder-overdue"]');
      await expect(expired).toHaveAttribute('data-placement', 'inbox-only');
      await expect(expired).toContainText('超过12小时');
      const policy = today(page).getByRole('region', { name: '晨报与联系', exact: true });
      await expect(policy).toContainText('07:00');
      await expect(policy).toContainText('不受免打扰时段限制');
      await expect(today(page).locator('.button.primary')).toHaveCount(1);
      expect(await today(page).innerText()).not.toMatch(
        /"schema"\s*:|owner_id|subject_id|birth\.|solar_datetime|longitude|latitude/,
      );
      await auditNight(page);
      await captureNight(page, `Q4-today-${width}-${theme}`, true);
    });
  }

test('浏览月份、选择日历日与流日日期分别独立，不改变今天和今日安排', async ({ page }) => {
  await openToday(page);
  const plans = today(page).getByRole('list', { name: '安排与提醒列表', exact: true });
  const originalPlans = await plans.innerText();
  await selection(page).fill('2026-10-22');
  await expect(today(page)).toHaveAttribute('data-view-date', '2026-10-22');
  await expect(today(page)).toHaveAttribute('data-load-state', 'ready');
  let calendar = page.getByRole('region', { name: '2026年10月日历', exact: true });
  await expect(calendar.locator('[data-date="2026-10-21"]')).toHaveAttribute('aria-current', 'date');
  await expect(calendar.locator('.calendar-mark')).toHaveCount(0);
  await calendar.getByRole('button', { name: '下个月', exact: true }).click();
  calendar = page.getByRole('region', { name: '2026年11月日历', exact: true });
  await calendar.locator('[data-date="2026-11-03"]').click();
  await expect(calendar.locator('[data-date="2026-11-03"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(today(page)).toHaveAttribute('data-today', '2026-10-21');
  await expect(today(page)).toHaveAttribute('data-view-date', '2026-10-22');
  expect(await plans.innerText()).toBe(originalPlans);
  await auditNight(page);
  await captureNight(page, 'Q4-today-separate-browsing-1440-light', true);
  await page.getByRole('button', { name: '回到今天', exact: true }).click();
  await expect(page.getByRole('region', { name: '2026年10月日历', exact: true })).toBeVisible();
  await expect(selection(page)).toHaveValue('2026-10-22');
  await page.getByRole('button', { name: '看今天的流日', exact: true }).click();
  await expect(selection(page)).toHaveValue('2026-10-21');
  await expect(today(page)).toHaveAttribute('data-load-state', 'ready');
});

test('未发布日期显示空状态而不借用别天的依据，今日安排仍保留', async ({ page }) => {
  await openToday(page, 390, 'dark');
  await selection(page).fill('2026-10-28');
  await expect(today(page)).toHaveAttribute('data-load-state', 'empty');
  await expect(today(page)).toHaveAttribute('data-today', '2026-10-21');
  await expect(today(page)).toContainText('这天还没有流日样例');
  await expect(today(page).locator('[data-daily-system]')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /^查看(?:八字|紫微|星盘)依据$/ })).toHaveCount(0);
  await expect(
    today(page).getByRole('list', { name: '安排与提醒列表', exact: true }).getByRole('listitem'),
  ).toHaveCount(3);
  await auditNight(page);
  await captureNight(page, 'Q4-today-empty-date-390-dark', true);
  await page.getByRole('button', { name: '看今天的流日', exact: true }).click();
  await expect(today(page)).toHaveAttribute('data-load-state', 'ready');
});

test('键盘打开白名单依据Sheet，Escape与返回均回焦且切日不显示旧依据', async ({ page }) => {
  await openToday(page, 390);
  const trigger = page.getByRole('button', { name: '查看八字依据', exact: true });
  await trigger.focus();
  await page.keyboard.press('Enter');
  let dialog = page.getByRole('dialog', { name: '八字流日依据', exact: true });
  await expect(dialog).toContainText('依据别名：r18 · 2026-10-21');
  expect(await dialog.innerText()).not.toMatch(/tool-[a-f0-9]{64}|birth\.|solar_datetime|1998-03-12/);
  await auditNight(page);
  await captureNight(page, 'Q4-today-evidence-390-light');
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await selection(page).fill('2026-10-22');
  await expect(today(page)).toHaveAttribute('data-load-state', 'ready');
  await trigger.focus();
  await page.keyboard.press('Enter');
  dialog = page.getByRole('dialog', { name: '八字流日依据', exact: true });
  await expect(dialog).toContainText('2026-10-22');
  await expect(dialog).not.toContainText('2026-10-21');
  await page.goBack();
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await expect(page).toHaveURL(/#\/today$/);
  await auditNight(page);
});

test('共享设置修改后今日预览同步跟进关闭，晨报仍按订阅时间解释', async ({ page }) => {
  await openToday(page, 390, 'dark');
  await page.getByRole('link', { name: '调整报告与联系设置', exact: true }).click();
  const settings = page.locator('[data-runtime="night-settings"]');
  await expect(settings).toBeVisible();
  const contact = settings.getByRole('region', { name: '主动联系', exact: true });
  await contact.getByRole('switch', { name: '跟进开关', exact: true }).click();
  await contact.getByRole('button', { name: '保存主动联系设置', exact: true }).click();
  await expect(contact.getByRole('status')).toContainText('已保存主动联系设置');
  await page
    .getByRole('navigation', { name: '底部导航', exact: true })
    .getByRole('link', { name: '今日', exact: true })
    .click();
  await expect(today(page)).toHaveAttribute('data-load-state', 'ready');
  const followup = today(page).locator('[data-plan-id="demo-followup-today"]');
  await expect(followup).toHaveAttribute('data-placement', 'paused');
  await expect(followup).toContainText('主动跟进已关闭');
  await expect(today(page).getByRole('region', { name: '晨报与联系', exact: true })).toContainText(
    '不受免打扰时段限制',
  );
  await auditNight(page);
  await captureNight(page, 'Q4-today-shared-settings-390-dark', true);
});

test.describe('跨时区浏览器', () => {
  test.use({ timezoneId: 'Asia/Tokyo' });
  test('东京已过午夜时，今日标题与到期计划仍使用北京时间当天', async ({ page }) => {
    await openToday(page, 1440, 'light', '2026-10-21T23:30:00+08:00');
    expect(await page.evaluate(() => new Date().getDate())).toBe(22);
    await expect(today(page)).toHaveAttribute('data-today', '2026-10-21');
    await expect(selection(page)).toHaveValue('2026-10-21');
    await expect(today(page).getByRole('heading', { name: /10月21日.*星期三/ })).toBeVisible();
    await expect(today(page).locator('[data-plan-id="demo-reminder-today"]')).toContainText('今天 09:00');
    await auditNight(page);
    await captureNight(page, 'Q4-today-beijing-tokyo-boundary-1440-light', true);
  });
});
