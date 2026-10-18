import { expect, test, type Page } from '@playwright/test';
import { assertNightQuiet, auditNight, captureNight, guardNight, openNight } from './night-helpers';

const guide = (page: Page) => page.locator('[data-runtime="night-onboarding"]');
const answer = (page: Page) => guide(page).getByRole('textbox', { name: '相识这轮回答', exact: true });
async function step(page: Page, expected: string, stage?: number) {
  await expect(guide(page)).toHaveAttribute('data-step', expected);
  if (stage) await expect(guide(page)).toHaveAttribute('data-stage', String(stage));
}
async function start(page: Page, known = false) {
  await openNight(page, 'chat');
  await page.getByRole('button', { name: known ? '已有资料继续演示' : '初次相识演示', exact: true }).click();
  await step(page, 'welcome', 1);
  await guide(page).getByRole('button', { name: '开始认识', exact: true }).click();
  await step(page, known ? 'birth' : 'user_name', known ? 3 : 2);
}
async function reply(page: Page, text: string, next: string, stage?: number) {
  await answer(page).fill(text);
  await guide(page).getByRole('button', { name: '发送回答', exact: true }).click();
  await step(page, next, stage);
}
async function names(page: Page) {
  await reply(page, '阿禾（合成称呼）', 'assistant_name', 2);
  await guide(page).getByRole('button', { name: '明镜', exact: true }).click();
  await step(page, 'birth', 3);
}
async function preferences(page: Page) {
  await reply(page, '最近在做合成作品集。', 'priorities', 4);
  await reply(page, '想把学习与休息安排得更规律。', 'directness', 5);
  await guide(page).getByRole('button', { name: '直说', exact: true }).click();
  await step(page, 'terminology', 5);
  await guide(page).getByRole('button', { name: '术语少一点', exact: true }).click();
  await step(page, 'answer_length', 5);
  await guide(page).getByRole('button', { name: '短一点', exact: true }).click();
  await step(page, 'outreach', 6);
}
async function contact(page: Page) {
  await start(page);
  await names(page);
  await guide(page).getByRole('button', { name: '暂时跳过', exact: true }).click();
  await step(page, 'current_life', 4);
  await preferences(page);
}
async function navigate(page: Page, target: 'me' | 'chat') {
  await page.evaluate((value) => {
    location.hash = `/${value}`;
  }, target);
  await expect(page).toHaveURL(new RegExp(`#/${target}$`));
}
async function storageText(page: Page) {
  return page.evaluate(() => JSON.stringify([localStorage, sessionStorage]));
}

test.beforeEach(({ page }) => guardNight(page));
test.afterEach(({ page }) => assertNightQuiet(page));

for (const theme of ['light', 'dark'])
  for (const width of [390, 1440]) {
    test(`七阶段依序、只问当前问题与小结 ${width} ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
      await start(page);
      await auditNight(page);
      await captureNight(page, `04-onboarding-names-${width}-${theme}`);
      await names(page);
      await expect(guide(page).getByRole('region', { name: '相识这轮问题' })).toHaveCount(0);
      await captureNight(page, `04-onboarding-birth-${width}-${theme}`);
      await guide(page).getByRole('button', { name: '暂时跳过', exact: true }).click();
      await step(page, 'current_life', 4);
      await preferences(page);
      const question = guide(page).getByRole('region', { name: '相识这轮问题' });
      await expect(question).toHaveCount(1);
      for (const label of ['可以', '晨报换个时间', '先别主动找我'])
        await expect(question.getByRole('button', { name: label, exact: true })).toBeEnabled();
      await expect(question).toContainText('不会启用真实飞书投递');
      await auditNight(page);
      await captureNight(page, `04-onboarding-contact-${width}-${theme}`);
      await question.getByRole('button', { name: '可以', exact: true }).click();
      await step(page, 'summary', 7);
      await expect(guide(page).getByRole('region', { name: '相识小结' })).toContainText('我目前了解到的你');
      await expect(guide(page).getByRole('region', { name: '相识小结' })).toContainText('阿禾（合成称呼）');
      await expect(guide(page).getByRole('region', { name: '相识小结' })).toContainText('最近在做合成作品集');
      await expect(guide(page).getByRole('region', { name: '相识小结' })).toContainText('直说、术语少一点、短一点');
      await expect(guide(page)).toContainText('见面礼还在等可核对的排盘结果。');
      await auditNight(page);
      await captureNight(page, `04-onboarding-summary-${width}-${theme}`);
      await guide(page).getByRole('button', { name: '完成相识', exact: true }).click();
      await step(page, 'done', 7);
      await expect(guide(page)).toHaveAttribute('data-status', 'complete');
    });
  }

test('暂停后跨页返回保留草稿、原会话与当前问题，继续才恢复', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await start(page);
  const id = await guide(page).getAttribute('data-session-id');
  await answer(page).fill('尚未确认的合成称呼草稿');
  await guide(page).getByRole('button', { name: '先到这里', exact: true }).click();
  await expect(guide(page)).toHaveAttribute('data-status', 'paused');
  await navigate(page, 'me');
  await expect(page.locator('[data-runtime="night-me"]')).toBeVisible();
  await navigate(page, 'chat');
  await expect(guide(page)).toHaveAttribute('data-session-id', id!);
  await expect(guide(page)).toHaveAttribute('data-status', 'paused');
  await step(page, 'user_name', 2);
  await captureNight(page, '04-onboarding-paused-390');
  await guide(page).getByRole('button', { name: '继续相识', exact: true }).click();
  await expect(answer(page)).toHaveValue('尚未确认的合成称呼草稿');
  await expect(guide(page)).toHaveAttribute('data-status', 'active');
});

test('出生卡取消零写入，日期部分确认不补时间地点且原值不进入聊天或存储', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await start(page);
  await names(page);
  const revision = await guide(page).getAttribute('data-birth-revision');
  expect(revision).not.toBeNull();
  await expect(guide(page)).toHaveAttribute('data-birth-status', 'unconfirmed');
  const trigger = guide(page).getByRole('button', { name: '补充出生资料', exact: true });
  await trigger.click();
  const card = page.getByRole('dialog', { name: '核对出生资料', exact: true });
  await expect(card.getByLabel('阳历出生日期', { exact: true })).toHaveValue('');
  await expect(card.getByLabel('当地出生时间', { exact: true })).toHaveValue('');
  await expect(card.getByLabel('出生地名称', { exact: true })).toHaveValue('');
  await card.getByLabel('阳历出生日期', { exact: true }).fill('2001-02-03');
  await expect(card.getByRole('button', { name: '确认并保存资料', exact: true })).toBeDisabled();
  await auditNight(page);
  await captureNight(page, '04-onboarding-birth-confirmation-390');
  await card.getByRole('button', { name: '取消', exact: true }).click();
  await expect(card).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await expect(guide(page)).toHaveAttribute('data-birth-revision', revision!);
  await expect(guide(page)).toHaveAttribute('data-birth-status', 'unconfirmed');
  await step(page, 'birth', 3);
  await trigger.click();
  await card.getByLabel('阳历出生日期', { exact: true }).fill('2001-02-03');
  await expect(card.getByLabel('当地出生时间', { exact: true })).toHaveValue('');
  await expect(card.getByLabel('出生地名称', { exact: true })).toHaveValue('');
  await card.getByRole('checkbox', { name: '我已核对并授权保存出生资料', exact: true }).check();
  await card.getByRole('button', { name: '确认并保存资料', exact: true }).click();
  await expect(card).toHaveCount(0);
  await step(page, 'current_life', 4);
  await expect(guide(page)).toHaveAttribute('data-birth-status', 'partial');
  await expect(guide(page)).toHaveAttribute('data-birth-revision', String(Number(revision) + 1));
  await expect(guide(page).locator('.chat-messages')).not.toContainText('2001-02-03');
  expect(await storageText(page)).not.toContain('2001-02-03');
  await preferences(page);
  await guide(page).getByRole('button', { name: '可以', exact: true }).click();
  await step(page, 'summary', 7);
  await expect(guide(page)).not.toContainText('2001-02-03');
  await expect(guide(page)).not.toContainText('00:00');
  await expect(guide(page)).toContainText('见面礼还在等可核对的排盘结果。');
});

test('晨报换时间独立确认有效HH:mm，仅保存本地偏好', async ({ page }) => {
  await contact(page);
  await guide(page).getByRole('button', { name: '晨报换个时间', exact: true }).click();
  await step(page, 'outreach_time', 6);
  await reply(page, '08:30', 'summary', 7);
  await expect(guide(page)).toContainText('08:30');
  await expect(guide(page)).not.toContainText('已启用真实飞书');
  await captureNight(page, '04-onboarding-contact-custom-1440');
});

test('拒绝主动联系也能完成相识，不会强迫开启或安排真实投递', async ({ page }) => {
  await contact(page);
  await guide(page).getByRole('button', { name: '先别主动找我', exact: true }).click();
  await step(page, 'summary', 7);
  await expect(guide(page)).toContainText('先别主动找我');
  await expect(guide(page)).not.toContainText('已启用真实飞书');
  await guide(page).getByRole('button', { name: '完成相识', exact: true }).click();
  await expect(guide(page)).toHaveAttribute('data-status', 'complete');
});

test('无痕暂停引导且不读取相识草稿，退出后仍需显式继续', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await start(page);
  const id = await guide(page).getAttribute('data-session-id');
  await answer(page).fill('相识草稿只在普通引导中');
  await page.getByRole('switch', { name: '侧栏无痕模式', exact: true }).click();
  const privateChat = page.locator('[data-privacy="incognito"]');
  await expect(privateChat).toBeVisible();
  await expect(guide(page)).toHaveCount(0);
  await expect(privateChat).not.toContainText('相识草稿只在普通引导中');
  await privateChat.getByRole('textbox', { name: '和明镜说说', exact: true }).fill('PRIVATE_GUIDE_SYNTHETIC');
  await privateChat.getByRole('button', { name: '退出无痕', exact: true }).click();
  await expect(guide(page)).toHaveAttribute('data-session-id', id!);
  await expect(guide(page)).toHaveAttribute('data-status', 'paused');
  await guide(page).getByRole('button', { name: '继续相识', exact: true }).click();
  await expect(answer(page)).toHaveValue('相识草稿只在普通引导中');
  await expect(guide(page)).not.toContainText('PRIVATE_GUIDE_SYNTHETIC');
  expect(await storageText(page)).not.toContain('PRIVATE_GUIDE_SYNTHETIC');
});

test('已有资料仅按显式known跳过称呼与偏好，未确认出生资料仍单独核对', async ({ page }) => {
  await start(page, true);
  await step(page, 'birth', 3);
  await expect(guide(page)).toHaveAttribute('data-birth-status', 'unconfirmed');
  await guide(page).getByRole('button', { name: '暂时跳过', exact: true }).click();
  await reply(page, '最近在整理合成笔记。', 'priorities', 4);
  await reply(page, '希望把一件正在做的事收好尾。', 'outreach', 6);
  await expect(guide(page)).not.toHaveAttribute('data-step', 'directness');
  await captureNight(page, '04-onboarding-known-contact-1440');
});
