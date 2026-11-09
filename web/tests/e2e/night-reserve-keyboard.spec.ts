import { expect, test, type Locator, type Page, type TestInfo } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { assertNightQuiet, auditNight, guardNight } from './night-helpers';

const origin = 'http://127.0.0.1:4173';
const review = (page: Page) => page.locator('[data-runtime="organize-v2"]');
const segment = (page: Page, id: number) => review(page).locator(`[data-segment-id="segment-${id}"]`);
const composer = (page: Page) => page.getByRole('textbox', { name: '和明镜说说', exact: true });
const conversation = (page: Page) => page.locator('[data-page="chat"][data-scenario]');
const queue = (page: Page) => page.getByRole('region', { name: '排队消息', exact: true });

async function tabTo(page: Page, target: Locator) {
  await expect(target).toBeVisible();
  for (let index = 0; index < 220; index++) {
    if (await target.evaluate((node) => node === document.activeElement)) return;
    await page.keyboard.press('Tab');
  }
  await expect(target, 'Target must be reachable through the actual Tab order').toBeFocused();
}
async function activate(page: Page, target: Locator) {
  await tabTo(page, target);
  await page.keyboard.press('Enter');
}
async function replaceText(page: Page, target: Locator, text: string) {
  await tabTo(page, target);
  await page.keyboard.press('ControlOrMeta+A');
  await page.keyboard.type(text);
}
async function screenshot(page: Page, name: string, info: TestInfo) {
  const directory = process.env.NIGHT_EVIDENCE_DIR ?? 'evidence/2026-10-21/reserve-keyboard';
  await fs.mkdir(directory, { recursive: true });
  const filename = path.join(directory, `${name}-${randomUUID().slice(0, 8)}.png`);
  await fs.writeFile(filename, await page.screenshot({ animations: 'disabled', fullPage: true }), { flag: 'wx' });
  info.annotations.push({ type: 'keyboard_screenshot', description: filename.replaceAll('\\', '/') });
}
async function open(page: Page, width: number, route: 'review' | 'chat' | 'today') {
  await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
  await page.addInitScript((theme) => localStorage.setItem('mingjing-theme', theme), width === 390 ? 'dark' : 'light');
  await page.goto(route === 'review' ? '/?spaces=demo#/organize-review' : `/?night=demo#/${route}`);
  await page.evaluate(() => document.fonts.ready);
  if (route === 'review') await expect(review(page)).toHaveAttribute('data-state', 'draft');
  else if (route === 'chat') await expect(conversation(page)).toHaveAttribute('data-complete', 'true');
  else await expect(page.locator('[data-runtime="night-today"]')).toHaveAttribute('data-load-state', 'ready');
}
async function insideDialog(page: Page, dialog: Locator) {
  for (let count = 0; count < 5; count++) {
    await page.keyboard.press('Tab');
    expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press('Shift+Tab');
  expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
}

test.beforeEach(async ({ page }) => {
  guardNight(page);
  await page.clock.setFixedTime(new Date('2026-10-21T07:15:00+08:00'));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (
      ['http:', 'https:'].includes(url.protocol) &&
      (url.origin !== origin || /^\/(?:api|__test__|__frontend_fixture__)(?:\/|$)/.test(url.pathname))
    )
      await route.abort();
    else await route.continue();
  });
});
test.afterEach(({ page }) => assertNightQuiet(page));

for (const width of [390, 1440]) {
  test(`键盘审阅：原话、嵌套选择器取消及接受后的焦点 ${width}`, async ({ page }, info) => {
    await open(page, width, 'review');
    const uncertain = segment(page, 1);
    const original = uncertain.locator('summary');
    await activate(page, original);
    await expect(uncertain.locator('details')).toHaveAttribute('open', '');
    await expect(uncertain).toContainText('想在周末留一段散步的时间。');
    const revision = await review(page).getAttribute('data-revision');
    const move = uncertain.getByRole('button', { name: '移动', exact: true });
    await activate(page, move);
    const dialog = page.getByRole('dialog', { name: '移动片段', exact: true });
    const spaces = dialog.getByRole('combobox', { name: '目标区', exact: true });
    await tabTo(page, spaces);
    await page.keyboard.press('ArrowDown');
    let list = page.getByRole('listbox', { name: '目标区', exact: true });
    await expect(list).toBeVisible();
    await page.keyboard.press('Home');
    await page.keyboard.press('End');
    await page.keyboard.press('Home');
    await page.keyboard.press('Enter');
    await expect(list).toHaveCount(0);
    await expect(spaces).toBeFocused();
    const topics = dialog.getByRole('combobox', { name: '目标话题', exact: true });
    await tabTo(page, topics);
    await page.keyboard.press('ArrowDown');
    list = page.getByRole('listbox', { name: '目标话题', exact: true });
    await expect(list).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(list).toHaveCount(0);
    await expect(dialog).toBeVisible();
    await expect(topics).toBeFocused();
    await auditNight(page);
    await screenshot(page, `reserve-review-nested-select-${width}`, info);
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(move).toBeFocused();
    await expect(review(page)).toHaveAttribute('data-revision', revision!);
    await activate(page, uncertain.getByRole('button', { name: '接受', exact: true }));
    await expect(
      page.getByRole('region', { name: '不确定，待你整理', exact: true }).locator('[data-segment-id="segment-1"]'),
    ).toHaveCount(0);
    // The accepted article moves between trees. Its removed button must not leave keyboard focus on body.
    expect(
      await page.evaluate(() => document.activeElement !== document.body && document.activeElement?.isConnected),
    ).toBe(true);
    await auditNight(page);
  });

  test(`键盘应用和字段撤销：二次确认、Space勾选与失效触发器回焦 ${width}`, async ({ page }, info) => {
    await open(page, width, 'review');
    for (const id of [2, 3]) await activate(page, segment(page, id).getByRole('button', { name: '接受', exact: true }));
    const apply = page.getByRole('button', { name: '应用已接受的整理', exact: true });
    const revision = await review(page).getAttribute('data-revision');
    await activate(page, apply);
    let dialog = page.getByRole('dialog', { name: '应用已接受的整理？', exact: true });
    await insideDialog(page, dialog);
    await activate(page, dialog.getByRole('button', { name: '取消', exact: true }));
    await expect(dialog).toHaveCount(0);
    await expect(apply).toBeFocused();
    await expect(review(page)).toHaveAttribute('data-revision', revision!);
    await page.keyboard.press('Enter');
    dialog = page.getByRole('dialog', { name: '应用已接受的整理？', exact: true });
    await activate(page, dialog.getByRole('button', { name: '确认应用', exact: true }));
    await expect(review(page)).toHaveAttribute('data-state', 'applied');
    const selected = page.getByRole('checkbox', {
      name: '选择撤销：面试准备 · 片段2第1条 · 归区与话题标签',
      exact: true,
    });
    await tabTo(page, selected);
    await page.keyboard.press('Space');
    await expect(selected).toBeChecked();
    const partial = page.getByRole('button', { name: '撤销所选字段', exact: true });
    await activate(page, partial);
    dialog = page.getByRole('dialog', { name: '撤销这部分整理？', exact: true });
    await activate(page, dialog.getByRole('button', { name: '取消', exact: true }));
    await expect(selected).toBeChecked();
    await expect(review(page)).toHaveAttribute('data-state', 'applied');
    await expect(partial).toBeFocused();
    await page.keyboard.press('Enter');
    dialog = page.getByRole('dialog', { name: '撤销这部分整理？', exact: true });
    await activate(page, dialog.getByRole('button', { name: '确认撤销', exact: true }));
    await expect(review(page)).toHaveAttribute('data-state', 'partially_reverted');
    await expect(selected).toHaveCount(0);
    await expect(page.getByRole('heading', { name: '旧对话审阅', exact: true })).toBeFocused();
    await auditNight(page);
    await screenshot(page, `reserve-review-partial-revert-${width}`, info);
    await activate(page, page.getByRole('button', { name: '撤销整批整理', exact: true }));
    dialog = page.getByRole('dialog', { name: '撤销这部分整理？', exact: true });
    await activate(page, dialog.getByRole('button', { name: '确认撤销', exact: true }));
    await expect(review(page)).toHaveAttribute('data-state', 'reverted');
    await expect(segment(page, 2)).toContainText('想练习怎样把项目经过说清楚。');
  });

  test(`键盘插话：Enter排队、Shift换行、停止、单项取消与顺序继续 ${width}`, async ({ page }, info) => {
    await open(page, width, 'chat');
    await activate(page, page.getByRole('button', { name: '查看插话排队', exact: true }));
    await expect(conversation(page)).toHaveAttribute('data-complete', 'false');
    await replaceText(page, composer(page), '键盘合成插话第一行');
    await page.keyboard.press('Shift+Enter');
    await page.keyboard.type('第二行仍在草稿');
    await expect(composer(page)).toHaveValue('键盘合成插话第一行\n第二行仍在草稿');
    await expect(queue(page)).toHaveCount(0);
    await page.keyboard.press('Enter');
    const canceled = queue(page).getByRole('listitem').filter({ hasText: '键盘合成插话第一行' });
    await expect(canceled).toHaveAttribute('data-queue-state', 'queued');
    await expect(queue(page).getByRole('listitem')).toHaveCount(1);
    const retained = '键盘合成插话第二条保留';
    await replaceText(page, composer(page), retained);
    await page.keyboard.press('Enter');
    await expect(queue(page).getByRole('listitem')).toHaveCount(2);
    await expect(queue(page).getByRole('listitem').last()).toHaveAttribute('data-queue-state', 'queued');
    const draft = '这段尚未提交的普通草稿';
    await replaceText(page, composer(page), draft);
    await page.keyboard.press('Tab');
    const stop = page.getByRole('button', { name: '停止回答', exact: true });
    await expect(stop).toBeFocused();
    await page.keyboard.press('Shift+Tab');
    await expect(composer(page)).toBeFocused();
    await expect(composer(page)).toHaveValue(draft);
    await page.keyboard.press('Tab');
    const began = Date.now();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('status').filter({ hasText: '已停止本地演示，排队消息仍保留' })).toBeVisible({
      timeout: 1500,
    });
    expect(Date.now() - began).toBeLessThan(2000);
    await expect(composer(page)).toBeFocused();
    await activate(page, canceled.getByRole('button', { name: '取消排队', exact: true }));
    await expect(canceled).toHaveCount(0);
    await expect(composer(page)).toBeFocused();
    await expect(queue(page).getByRole('listitem')).toHaveCount(1);
    await expect(composer(page)).toHaveValue(draft);
    await auditNight(page);
    await screenshot(page, `reserve-queue-stopped-canceled-${width}`, info);
    await activate(page, page.getByRole('button', { name: '继续处理下一条', exact: true }));
    await expect(conversation(page)).toHaveAttribute('data-scenario', 'queued');
    await expect(conversation(page)).toHaveAttribute('data-complete', 'true');
    await expect(queue(page)).toHaveCount(0);
    await expect(composer(page)).toHaveValue(draft);
    const messages = conversation(page).getByRole('article', { name: '你说的', exact: true });
    await expect(messages).toHaveCount(2);
    await expect(messages.last()).toContainText(retained);
    await expect(conversation(page)).not.toContainText('键盘合成插话第一行');
    expect(
      await page.evaluate(() => document.activeElement !== document.body && document.activeElement?.isConnected),
    ).toBe(true);
  });

  test(`键盘今日：月历、依据弹层及设置往返主动作 ${width}`, async ({ page }, info) => {
    await open(page, width, 'today');
    const today = page.locator('[data-runtime="night-today"]');
    const trigger = page.getByRole('button', { name: '查看本月日历', exact: true });
    if (width < 1024) await activate(page, trigger);
    const calendar =
      width < 1024 ? page.getByRole('dialog', { name: '本月日历', exact: true }) : page.locator('.today-calendar');
    await activate(page, calendar.getByRole('button', { name: '下个月', exact: true }));
    await expect(calendar.getByRole('region', { name: '2026年11月日历', exact: true })).toBeVisible();
    await activate(page, calendar.getByRole('button', { name: '上个月', exact: true }));
    const chosen = calendar.locator('button[data-date="2026-10-22"]');
    await activate(page, chosen);
    await expect(chosen).toHaveAttribute('aria-pressed', 'true');
    await activate(page, calendar.getByRole('button', { name: '回到今天', exact: true }));
    await expect(calendar.locator('button[data-date="2026-10-21"]')).toHaveAttribute('aria-pressed', 'true');
    if (width < 1024) {
      await page.keyboard.press('Escape');
      await expect(calendar).toHaveCount(0);
      await expect(trigger).toBeFocused();
    }
    await expect(today).toHaveAttribute('data-today', '2026-10-21');
    await expect(today.getByLabel('查看哪天的流日', { exact: true })).toHaveValue('2026-10-21');
    const evidence = page.getByRole('button', { name: '查看八字依据', exact: true });
    await activate(page, evidence);
    const dialog = page.getByRole('dialog', { name: '八字流日依据', exact: true });
    await insideDialog(page, dialog);
    await expect(dialog).toContainText('2026-10-21');
    await auditNight(page);
    await screenshot(page, `reserve-today-evidence-${width}`, info);
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(evidence).toBeFocused();
    await activate(page, page.getByRole('link', { name: '调整报告与联系设置', exact: true }));
    const settings = page.locator('[data-runtime="night-settings"]');
    await expect(settings).toBeVisible();
    const followup = settings.getByRole('switch', { name: '跟进开关', exact: true });
    await tabTo(page, followup);
    await page.keyboard.press('Space');
    await expect(followup).not.toBeChecked();
    await activate(page, settings.getByRole('button', { name: '保存主动联系设置', exact: true }));
    await expect(settings.getByRole('status')).toContainText('已保存主动联系设置');
    const nav = page.locator(width < 1024 ? '.tabbar' : '.rail');
    await activate(page, nav.getByRole('link', { name: '今日', exact: true }));
    await expect(today).toHaveAttribute('data-load-state', 'ready');
    await expect(today.locator('[data-plan-id="demo-followup-today"]')).toHaveAttribute('data-placement', 'paused');
    await activate(page, today.getByRole('link', { name: '和明镜聊聊', exact: true }));
    await expect(conversation(page)).toHaveAttribute('data-complete', 'true');
    await tabTo(page, composer(page));
    await expect(composer(page)).toBeFocused();
    await auditNight(page);
  });
}
