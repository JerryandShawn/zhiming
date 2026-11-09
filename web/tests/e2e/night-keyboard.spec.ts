import { expect, test, type Locator, type Page } from '@playwright/test';
import { assertNightQuiet, auditNight, captureNight, guardNight, openNight } from './night-helpers';

async function tabUntil(page: Page, target: Locator) {
  await expect(target).toBeVisible();
  for (let index = 0; index < 70; index++) {
    if (await target.evaluate((node) => node === document.activeElement)) return;
    await page.keyboard.press('Tab');
  }
  await expect(target).toBeFocused();
}
async function typeOver(page: Page, value: string) {
  await page.keyboard.press('ControlOrMeta+A');
  await page.keyboard.type(value);
}
async function birthStep(page: Page) {
  const entry = page.getByRole('button', { name: '已有资料继续演示', exact: true });
  await tabUntil(page, entry);
  await page.keyboard.press('Enter');
  const guide = page.locator('[data-runtime="night-onboarding"]');
  await expect(guide).toHaveAttribute('data-step', 'welcome');
  await tabUntil(page, guide.getByRole('button', { name: '开始认识', exact: true }));
  await page.keyboard.press('Enter');
  await expect(guide).toHaveAttribute('data-step', 'birth');
  const trigger = guide.getByRole('button', { name: '补充出生资料', exact: true });
  await tabUntil(page, trigger);
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog', { name: '核对出生资料', exact: true })).toBeVisible();
  return { guide, trigger };
}
async function noMotion(dialog: Locator) {
  const styles = await dialog.evaluate((node) => {
    const css = getComputedStyle(node);
    return { animation: css.animationDuration, transition: css.transitionDuration };
  });
  for (const durations of Object.values(styles))
    expect(
      durations.split(',').every((duration) => Number.parseFloat(duration) === 0),
      JSON.stringify(styles),
    ).toBe(true);
}

test.beforeEach(async ({ page }) => {
  guardNight(page);
  await page.setViewportSize({ width: 390, height: 844 });
});
test.afterEach(({ page }) => assertNightQuiet(page));

test('全键盘画像：Tab编辑、Escape取消回焦，再确认保存并回焦', async ({ page }) => {
  await openNight(page, 'me');
  const root = page.locator('[data-runtime="night-me"]');
  const item = root.locator('[data-profile-id="profile-basic"]');
  const edit = item.getByRole('button', { name: '编辑画像条目：称呼与基本情况', exact: true });
  const revision = await root.getAttribute('data-revision');
  await tabUntil(page, edit);
  await page.keyboard.press('Enter');
  let dialog = page.getByRole('dialog', { name: '修改画像条目', exact: true });
  await tabUntil(page, dialog.getByRole('textbox', { name: '你的说法', exact: true }));
  await typeOver(page, '键盘取消后不应保存的合成草稿');
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(edit).toBeFocused();
  await expect(root).toHaveAttribute('data-revision', revision!);
  await expect(item).not.toContainText('键盘取消后不应保存的合成草稿');
  await page.keyboard.press('Enter');
  dialog = page.getByRole('dialog', { name: '修改画像条目', exact: true });
  await tabUntil(page, dialog.getByRole('textbox', { name: '你的说法', exact: true }));
  await typeOver(page, '键盘确认的合成称呼与近况');
  await tabUntil(page, dialog.getByRole('button', { name: '保存修改', exact: true }));
  await page.keyboard.press('Enter');
  await expect(dialog).toHaveCount(0);
  await expect(edit).toBeFocused();
  await expect(item).toContainText('键盘确认的合成称呼与近况');
  await expect(item.getByText('你改过', { exact: true })).toBeVisible();
  await auditNight(page);
  await captureNight(page, '08-keyboard-profile-confirmed-390');
});

test('全键盘出生卡：取消零确认，日期授权后推进且原值不进入转录', async ({ page }) => {
  await openNight(page, 'chat');
  const { guide, trigger } = await birthStep(page);
  let dialog = page.getByRole('dialog', { name: '核对出生资料', exact: true });
  await tabUntil(page, dialog.getByRole('textbox', { name: '阳历出生日期', exact: true }));
  await typeOver(page, '1998-03-12');
  await expect(dialog.getByRole('button', { name: '确认并保存资料', exact: true })).toBeDisabled();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await expect(guide).toHaveAttribute('data-birth-revision', '0');
  await page.keyboard.press('Enter');
  dialog = page.getByRole('dialog', { name: '核对出生资料', exact: true });
  await tabUntil(page, dialog.getByRole('textbox', { name: '阳历出生日期', exact: true }));
  await typeOver(page, '1998-03-12');
  const consent = dialog.getByRole('checkbox', { name: '我已核对并授权保存出生资料', exact: true });
  await tabUntil(page, consent);
  await page.keyboard.press('Space');
  await expect(consent).toBeChecked();
  await tabUntil(page, dialog.getByRole('button', { name: '确认并保存资料', exact: true }));
  await page.keyboard.press('Enter');
  await expect(dialog).toHaveCount(0);
  await expect(guide).toHaveAttribute('data-step', 'current_life');
  await expect(guide).toHaveAttribute('data-birth-status', 'partial');
  await expect(guide.getByRole('textbox', { name: '相识这轮回答', exact: true })).toBeFocused();
  await expect(guide).not.toContainText('1998-03-12');
  await auditNight(page);
  await captureNight(page, '08-keyboard-birth-confirmed-390');
});

test('减少动效时两个资料Sheet的实际动画与过渡时长为零', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openNight(page, 'me');
  expect(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true);
  const edit = page.getByRole('button', { name: '编辑画像条目：称呼与基本情况', exact: true });
  await tabUntil(page, edit);
  await page.keyboard.press('Enter');
  let dialog = page.getByRole('dialog', { name: '修改画像条目', exact: true });
  await expect(dialog).toBeVisible();
  await noMotion(dialog);
  await auditNight(page);
  await captureNight(page, '08-reduced-motion-profile-sheet-390');
  await page.keyboard.press('Escape');
  await expect(edit).toBeFocused();
  const chat = page
    .getByRole('navigation', { name: '底部导航', exact: true })
    .getByRole('link', { name: '对话', exact: true });
  await tabUntil(page, chat);
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#\/chat$/);
  const { trigger } = await birthStep(page);
  dialog = page.getByRole('dialog', { name: '核对出生资料', exact: true });
  await noMotion(dialog);
  await auditNight(page);
  await captureNight(page, '08-reduced-motion-birth-sheet-390');
  await page.keyboard.press('Escape');
  await expect(trigger).toBeFocused();
});
