import { expect, test, type Page } from '@playwright/test';
import { assertNightQuiet, auditNight, captureNight, guardNight, openNight } from './night-helpers';

test.use({ timezoneId: 'Asia/Shanghai' });
test.beforeEach(({ page }) => guardNight(page));
test.afterEach(({ page }) => assertNightQuiet(page));

const conversation = (page: Page) => page.locator('[data-page="chat"][data-scenario]');
const input = (page: Page) => page.getByRole('textbox', { name: '和明镜说说', exact: true });
const queue = (page: Page) => page.getByRole('region', { name: '排队消息', exact: true });
const queuedItem = (page: Page, text: string) => queue(page).getByRole('listitem').filter({ hasText: text });
async function startStreaming(page: Page, width = 1440, theme = 'light') {
  await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
  await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
  await openNight(page);
  await expect(conversation(page)).toHaveAttribute('data-complete', 'true');
  await page.getByRole('button', { name: '查看插话排队', exact: true }).click();
  await expect(conversation(page)).toHaveAttribute('data-scenario', 'streaming');
  await expect(conversation(page)).toHaveAttribute('data-complete', 'false');
  await expect(page.getByRole('button', { name: '停止回答', exact: true })).toBeVisible();
}
async function enqueue(page: Page, text: string) {
  await input(page).fill(text);
  await page.getByRole('button', { name: '排队发送', exact: true }).click();
  const item = queuedItem(page, text);
  await expect(item).toHaveAttribute('data-queue-state', 'queued');
  await expect(item.getByRole('status')).toHaveText('已收到，这段说完一起看');
  await expect(input(page)).toHaveValue('');
  return item;
}

for (const theme of ['light', 'dark'])
  for (const width of [390, 1440]) {
    test(`回答中可继续输入、确认排队与停止同时可达 ${width} ${theme}`, async ({ page }) => {
      await startStreaming(page, width, theme);
      await expect(input(page)).toBeEnabled();
      await expect(page.getByRole('button', { name: '添加图片', exact: true })).toBeEnabled();
      const text = `合成插话排队 ${width} ${theme}`;
      const item = await enqueue(page, text);
      const draft = '这一条还在编辑，不应跟上一条一起清空';
      await input(page).fill(draft);
      await expect(input(page)).toHaveValue(draft);
      await expect(page.getByRole('button', { name: '排队发送', exact: true })).toBeEnabled();
      await expect(page.getByRole('button', { name: '停止回答', exact: true })).toBeEnabled();
      await item.scrollIntoViewIfNeeded();
      await auditNight(page);
      await captureNight(page, `Q3-queue-received-${width}-${theme}`);
      await page.getByRole('button', { name: '停止回答', exact: true }).click();
      await expect(page.getByRole('status').filter({ hasText: '已停止本地演示，排队消息仍保留' })).toBeVisible();
      await expect(item).toHaveAttribute('data-queue-state', 'queued');
      await expect(input(page)).toHaveValue(draft);
    });
  }

test('两条插话按接收顺序继续，前轮正文与两条新消息都保留', async ({ page }) => {
  await startStreaming(page);
  const first = '合成队列第一条：先核对项目经过';
  const second = '合成队列第二条：再梳理沟通顺序';
  await enqueue(page, first);
  await enqueue(page, second);
  await expect(queue(page).getByRole('listitem')).toHaveCount(2);
  await expect(conversation(page)).toHaveAttribute('data-scenario', 'queued', { timeout: 12000 });
  await expect(queue(page)).toHaveCount(0, { timeout: 12000 });
  await expect(conversation(page)).toHaveAttribute('data-complete', 'true', { timeout: 12000 });
  const messages = conversation(page).getByRole('article', { name: '你说的', exact: true });
  await expect(messages).toHaveCount(3);
  const texts = await messages.allTextContents();
  expect(texts[0]).toContain('有两个方向拿不定主意');
  expect(texts[1]).toContain(first);
  expect(texts[2]).toContain(second);
  const history = conversation(page).locator('[data-demo-turn]');
  await expect(history).toHaveCount(2);
  await expect(history.first()).toContainText('我先把这段话慢慢说完。');
  await expect(history.nth(1)).toContainText('这条补充已接到当前对话后面。');
  await auditNight(page);
  await captureNight(page, 'Q3-queue-fifo-history-1440-light');
});

test('两条排队可只取消其中一条，余下消息随后处理且不复活已取消项', async ({ page }) => {
  await startStreaming(page, 390, 'dark');
  const canceled = '合成取消项：这一条先不用接着说';
  const retained = '合成保留项：只继续核对这一条';
  const first = await enqueue(page, canceled);
  await enqueue(page, retained);
  await first.getByRole('button', { name: '取消排队', exact: true }).click();
  await expect(first).toHaveCount(0);
  await expect(input(page)).toBeFocused();
  await expect(queue(page).getByRole('listitem')).toHaveCount(1);
  await expect(queuedItem(page, retained)).toHaveAttribute('data-queue-state', 'queued');
  await auditNight(page);
  await captureNight(page, 'Q3-queue-cancel-one-390-dark');
  await expect(conversation(page)).toHaveAttribute('data-scenario', 'queued', { timeout: 12000 });
  await expect(conversation(page)).toHaveAttribute('data-complete', 'true', { timeout: 12000 });
  await expect(queue(page)).toHaveCount(0);
  const messages = conversation(page).getByRole('article', { name: '你说的', exact: true });
  await expect(messages).toHaveCount(2);
  await expect(messages.last()).toContainText(retained);
  await expect(conversation(page)).not.toContainText(canceled);
  await expect(conversation(page).locator('[data-demo-turn]').first()).toContainText('我先把这段话慢慢说完。');
  await auditNight(page);
  await captureNight(page, 'Q3-queue-cancel-continued-390-dark');
});

test('停止在两秒内反馈，队列保留且只在手动继续后处理', async ({ page }, info) => {
  await startStreaming(page);
  const text = '合成停止后保留的插话';
  const item = await enqueue(page, text);
  const started = Date.now();
  await page.getByRole('button', { name: '停止回答', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: '已停止本地演示，排队消息仍保留' })).toBeVisible({
    timeout: 1500,
  });
  const elapsed = Date.now() - started;
  info.annotations.push({ type: 'stop_feedback_ms', description: String(elapsed) });
  expect(elapsed).toBeLessThan(2000);
  await expect(input(page)).toBeFocused();
  await expect(item).toHaveAttribute('data-queue-state', 'queued');
  await expect(page.getByRole('button', { name: '停止回答', exact: true })).toHaveCount(0);
  await page.waitForTimeout(2200);
  await expect(conversation(page)).toHaveAttribute('data-scenario', 'streaming');
  await expect(item).toHaveAttribute('data-queue-state', 'queued');
  await auditNight(page);
  await captureNight(page, 'Q3-queue-stopped-retained-1440-light');
  await page.getByRole('button', { name: '继续处理下一条', exact: true }).click();
  await expect(conversation(page)).toHaveAttribute('data-scenario', 'queued');
  await expect(conversation(page)).toHaveAttribute('data-complete', 'true');
  await expect(queue(page)).toHaveCount(0);
  await expect(conversation(page).getByRole('article', { name: '你说的', exact: true }).last()).toContainText(text);
  await auditNight(page);
  await captureNight(page, 'Q3-queue-manual-continued-1440-light');
});

test('切换无痕清空普通排队，退出仍保留未提交的普通草稿', async ({ page }) => {
  await startStreaming(page, 390, 'dark');
  const text = '合成进入无痕前的排队消息';
  await enqueue(page, text);
  const draft = '普通草稿只在当前页面保留 Q3_NORMAL_DRAFT';
  await input(page).fill(draft);
  await page.getByRole('switch', { name: '无痕模式', exact: true }).click();
  const privateChat = page.locator('[data-privacy="incognito"]');
  await expect(privateChat).toBeVisible();
  await expect(input(page)).toHaveValue('');
  await expect(queue(page)).toHaveCount(0);
  await expect(privateChat).not.toContainText(text);
  await expect(privateChat).not.toContainText(draft);
  await auditNight(page);
  await captureNight(page, 'Q3-queue-cleared-private-390-dark');
  await page.getByRole('button', { name: '退出无痕', exact: true }).click();
  await expect(privateChat).toHaveCount(0);
  await expect(input(page)).toHaveValue(draft);
  await expect(queue(page)).toHaveCount(0);
  await expect(
    conversation(page).getByRole('article', { name: '你说的', exact: true }).filter({ hasText: text }),
  ).toHaveCount(0);
  const stored = await page.evaluate(() => [localStorage, sessionStorage].flatMap((storage) => Object.values(storage)));
  expect(stored.join('\n')).not.toContain(text);
  expect(stored.join('\n')).not.toContain(draft);
  await auditNight(page);
  await captureNight(page, 'Q3-queue-ordinary-draft-restored-390-dark');
});
