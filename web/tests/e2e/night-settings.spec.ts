import { expect, test, type Page } from '@playwright/test';
import { assertNightQuiet, auditNight, captureNight, guardNight, openNight } from './night-helpers';

const settings = (page: Page) => page.locator('[data-runtime="night-settings"]');
const report = (page: Page, kind: string) => settings(page).locator(`[data-report-kind="${kind}"]`);
const reports = [
  ['daily', '晨报'],
  ['weekly', '周报'],
  ['monthly', '月报'],
  ['quarterly', '季报'],
] as const;

async function select(page: Page, label: string, value: string, caption: string) {
  const control = page.getByLabel(label, { exact: true });
  if (await control.evaluate((element) => element.tagName === 'SELECT')) await control.selectOption(value);
  else {
    await control.click();
    await page.getByRole('option', { name: caption, exact: true }).click();
  }
}
async function navigate(page: Page, target: 'chat' | 'settings') {
  await page.evaluate((value) => {
    location.hash = `/${value}`;
  }, target);
  await expect(page).toHaveURL(new RegExp(`#/${target}$`));
}

test.beforeEach(({ page }) => guardNight(page));
test.afterEach(({ page }) => assertNightQuiet(page));

for (const theme of ['light', 'dark'])
  for (const width of [390, 1440]) {
    test(`设置分组、报告表单和主题审计 ${width} ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
      await openNight(page, 'settings');
      await expect(settings(page)).toBeVisible();
      for (const [kind, name] of reports) {
        await expect(report(page, kind).getByRole('heading', { name, exact: true })).toBeVisible();
        await expect(report(page, kind).getByLabel(`${name}发送时间`, { exact: true })).toHaveValue('07:00');
      }
      await expect(settings(page)).toContainText('北京时间');
      await expect(settings(page)).toContainText('15');
      await expect(settings(page)).toContainText('无痕');
      await expect(settings(page).getByRole('link', { name: '让明镜忘掉某段时间', exact: true })).toHaveAttribute(
        'href',
        '#/me?section=memory',
      );
      await auditNight(page);
      await captureNight(page, `05-settings-${width}-${theme}`, true);
      const opposite = theme === 'light' ? 'dark' : 'light';
      await settings(page)
        .getByRole('button', { name: opposite === 'dark' ? '夜墨' : '宣纸', exact: true })
        .click();
      await expect(page.locator('html')).toHaveAttribute('data-theme', opposite);
      expect(await page.evaluate(() => localStorage.getItem('mingjing-theme'))).toBe(opposite);
      await settings(page)
        .getByRole('button', { name: theme === 'dark' ? '夜墨' : '宣纸', exact: true })
        .click();
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await expect(settings(page)).toHaveAttribute('data-revision', '1');
    });
  }

for (const [kind, name] of reports) {
  test(`${name}只在确认后修改，取消零写入并保存对应周期字段`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openNight(page, 'settings');
    const row = report(page, kind);
    const time = row.getByLabel(`${name}发送时间`, { exact: true });
    await expect(row).toHaveAttribute('data-revision', '1');
    await time.fill('08:30');
    await expect(settings(page)).toHaveAttribute('data-revision', '1');
    await row.getByRole('button', { name: '取消修改', exact: true }).click();
    await expect(time).toHaveValue('07:00');
    await expect(settings(page)).toHaveAttribute('data-revision', '1');
    const enabled = row.getByRole('switch', { name: `启用${name}`, exact: true });
    if (kind === 'monthly' || kind === 'quarterly') await enabled.click();
    await time.fill('08:30');
    if (kind === 'weekly') await select(page, '周报星期', '3', '星期三');
    if (kind === 'monthly' || kind === 'quarterly') {
      const date = row.getByLabel(`${name}日期`, { exact: true });
      if (await date.evaluate((element) => element.tagName === 'SELECT')) {
        await expect(date.locator('option[value="29"], option[value="30"], option[value="31"]')).toHaveCount(0);
      }
      await select(page, `${name}日期`, 'last', '月末（最后一天）');
    }
    if (kind === 'quarterly') await expect(row).toContainText(/1.*4.*7.*10/);
    await expect(row).toHaveAttribute('data-revision', '1');
    await row.getByRole('button', { name: `保存${name}设置`, exact: true }).click();
    await expect(row).toHaveAttribute('data-revision', '2');
    await expect(settings(page)).toHaveAttribute('data-revision', '2');
    await expect(row.getByRole('status')).toContainText(`已保存${name}设置`);
    await expect(time).toHaveValue('08:30');
    for (const [other] of reports.filter(([value]) => value !== kind))
      await expect(report(page, other)).toHaveAttribute('data-revision', '1');
    await captureNight(page, `05-report-${kind}-saved-390`);
    await navigate(page, 'chat');
    await navigate(page, 'settings');
    await expect(report(page, kind).getByLabel(`${name}发送时间`, { exact: true })).toHaveValue('08:30');
    if (kind === 'weekly') {
      const choice = page.getByLabel('周报星期', { exact: true });
      if (await choice.evaluate((element) => element.tagName === 'SELECT')) await expect(choice).toHaveValue('3');
      else await expect(choice).toHaveText('星期三');
    }
    if (kind === 'monthly' || kind === 'quarterly') {
      const choice = page.getByLabel(`${name}日期`, { exact: true });
      if (await choice.evaluate((element) => element.tagName === 'SELECT')) await expect(choice).toHaveValue('last');
      else await expect(choice).toHaveText('月末（最后一天）');
    }
  });
}

test('主动联系cap与DND保存跨页保留，相识拒绝联系同步关闭设置而不覆盖DND', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openNight(page, 'settings');
  const root = settings(page);
  await root
    .getByRole('group', { name: '每天最多联系次数', exact: true })
    .getByRole('button', { name: '3次', exact: true })
    .click();
  await root.getByLabel('免打扰开始时间', { exact: true }).fill('23:15');
  await root.getByLabel('免打扰结束时间', { exact: true }).fill('07:45');
  await expect(root).toHaveAttribute('data-revision', '1');
  await root.getByRole('button', { name: '保存主动联系设置', exact: true }).click();
  await expect(root).toHaveAttribute('data-revision', '2');
  await navigate(page, 'chat');
  await navigate(page, 'settings');
  await expect(
    root.getByRole('group', { name: '每天最多联系次数' }).getByRole('button', { name: '3次', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
  await expect(root.getByLabel('免打扰开始时间', { exact: true })).toHaveValue('23:15');
  await expect(root.getByLabel('免打扰结束时间', { exact: true })).toHaveValue('07:45');
  await captureNight(page, '05-contact-saved-390', true);
  await navigate(page, 'chat');
  await page.getByRole('button', { name: '已有资料继续演示', exact: true }).click();
  const guide = page.locator('[data-runtime="night-onboarding"]');
  await guide.getByRole('button', { name: '开始认识', exact: true }).click();
  for (const expected of ['birth', 'current_life', 'priorities']) {
    await expect(guide).toHaveAttribute('data-step', expected);
    await guide.getByRole('button', { name: '暂时跳过', exact: true }).click();
  }
  await expect(guide).toHaveAttribute('data-step', 'outreach');
  await guide.getByRole('button', { name: '先别主动找我', exact: true }).click();
  await expect(guide).toHaveAttribute('data-step', 'summary');
  await navigate(page, 'settings');
  await expect(root).toHaveAttribute('data-revision', '3');
  await expect(root.getByRole('switch', { name: '跟进开关', exact: true })).not.toBeChecked();
  for (const [kind, name] of reports)
    await expect(report(page, kind).getByRole('switch', { name: `启用${name}`, exact: true })).not.toBeChecked();
  await expect(root.getByLabel('免打扰开始时间', { exact: true })).toHaveValue('23:15');
  await expect(root.getByLabel('免打扰结束时间', { exact: true })).toHaveValue('07:45');
  await expect(
    root.getByRole('group', { name: '每天最多联系次数' }).getByRole('button', { name: '3次', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
});

test('设备吊销先确认、取消零写入，当前设备不可吊销且其他设备不受影响', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openNight(page, 'settings');
  const current = settings(page).locator('[data-device-id="mock-current"]');
  const phone = settings(page).locator('[data-device-id="mock-phone"]');
  const tablet = settings(page).locator('[data-device-id="mock-tablet"]');
  await expect(current.getByRole('button', { name: '吊销此设备', exact: true })).toBeDisabled();
  await phone.getByRole('button', { name: '吊销此设备', exact: true }).click();
  const confirm = page.getByRole('dialog', { name: '吊销这台设备？', exact: true });
  await expect(confirm).toBeVisible();
  await expect(phone).toHaveAttribute('data-status', 'active');
  await auditNight(page);
  await captureNight(page, '05-device-revoke-confirm-1440');
  await confirm.getByRole('button', { name: '取消', exact: true }).click();
  await expect(confirm).toHaveCount(0);
  await expect(settings(page)).toHaveAttribute('data-revision', '1');
  await expect(phone).toHaveAttribute('data-status', 'active');
  await phone.getByRole('button', { name: '吊销此设备', exact: true }).click();
  await confirm.getByRole('button', { name: '确认吊销（本地演示）', exact: true }).click();
  await expect(phone).toHaveAttribute('data-status', 'revoked');
  await expect(settings(page)).toHaveAttribute('data-revision', '2');
  await expect(current).toHaveAttribute('data-status', 'active');
  await expect(tablet).toHaveAttribute('data-status', 'active');
  await captureNight(page, '05-device-revoked-1440', true);
});
