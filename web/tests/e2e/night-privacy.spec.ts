import { expect, test, type Locator, type Page } from '@playwright/test';
import { deflateSync } from 'node:zlib';
import { installViewportSimulation, patchViewport, safeArea } from './components-embed-helpers';
import { assertNightQuiet, auditNight, captureNight, guardNight, openNight } from './night-helpers';

type StorageWindow = Window & { __nightPrivacyWrites?: string[] };
const privateRoot = (page: Page) => page.locator('[data-privacy="incognito"]');
const input = (page: Page) => page.getByRole('textbox', { name: '和明镜说说', exact: true });
const attachments = (page: Page) => page.getByRole('list', { name: '本轮附图', exact: true });
const privacySwitch = (page: Page) => page.getByRole('switch', { name: '无痕模式', exact: true });
const exit = (page: Page) => page.getByRole('button', { name: '退出无痕', exact: true });

// Two distinct, valid local PNGs make an accidental ordinary/private image swap observable.
function png(red: number, green: number, blue: number) {
  const chunk = (name: string, data: Buffer) => {
    const body = Buffer.concat([Buffer.from(name), data]);
    let checksum = 0xffffffff;
    for (const byte of body) {
      checksum ^= byte;
      for (let bit = 0; bit < 8; bit++) checksum = (checksum >>> 1) ^ (checksum & 1 ? 0xedb88320 : 0);
    }
    const length = Buffer.alloc(4),
      crc = Buffer.alloc(4);
    length.writeUInt32BE(data.length);
    crc.writeUInt32BE((checksum ^ 0xffffffff) >>> 0);
    return Buffer.concat([length, body, crc]);
  };
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk('IHDR', Buffer.from([0, 0, 0, 1, 0, 0, 0, 1, 8, 6, 0, 0, 0])),
    chunk('IDAT', deflateSync(Buffer.from([0, red, green, blue, 255]))),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}
const ordinaryImage = png(30, 100, 180),
  privateImage = png(180, 45, 90);
const imageUrl = (buffer: Buffer) => `data:image/png;base64,${buffer.toString('base64')}`;

async function attach(page: Page, buffer: Buffer, name: string) {
  await page.getByLabel('选择本轮图片', { exact: true }).setInputFiles({ name, mimeType: 'image/png', buffer });
  await expect(attachments(page).locator('img')).toHaveAttribute('src', imageUrl(buffer));
}
async function enter(page: Page) {
  const previousUrl = page.url();
  await privacySwitch(page).click();
  await expect(privateRoot(page)).toBeVisible();
  await expect(page).toHaveURL(previousUrl);
  await expect(input(page)).toHaveValue('');
  await expect(attachments(page)).toHaveCount(0);
  const id = await privateRoot(page).getAttribute('data-thread-id');
  expect(id).toMatch(/^incognito:[0-9a-f-]{36}$/i);
  return id;
}
async function normalReady(page: Page) {
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  await expect(input(page)).toBeEnabled();
}
async function assertUnstored(page: Page, ...secrets: string[]) {
  const observed = await page.evaluate(() => {
    const dump = (store: Storage) =>
      Array.from({ length: store.length }, (_, index) => {
        const key = store.key(index)!;
        return [key, store.getItem(key)];
      });
    return JSON.stringify({
      local: dump(localStorage),
      session: dump(sessionStorage),
      writes: (window as StorageWindow).__nightPrivacyWrites ?? [],
    });
  });
  for (const secret of secrets) expect(observed).not.toContain(secret);
}
async function reachable(control: Locator, top: number, bottom: number) {
  await expect(control).toBeVisible();
  await expect(control).toBeInViewport({ ratio: 1 });
  const box = await control.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.y).toBeGreaterThanOrEqual(top - 1);
  expect(box!.y + box!.height).toBeLessThanOrEqual(bottom + 1);
  await control.click({ trial: true });
}

test.beforeEach(async ({ page }) => {
  guardNight(page);
  // Observe failures with guardNight, and block them before an unintended request can leave the preview.
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (
      /^\/api(?:\/|$)/.test(url.pathname) ||
      (['http:', 'https:'].includes(url.protocol) && url.origin !== 'http://127.0.0.1:4173')
    )
      await route.abort('blockedbyclient');
    else await route.continue();
  });
  await page.addInitScript(() => {
    const writes: string[] = [];
    Object.defineProperty(window, '__nightPrivacyWrites', { value: writes });
    const setItem = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key: string, value: string) {
      writes.push(JSON.stringify([this === localStorage ? 'local' : 'session', key, value]));
      setItem.call(this, key, value);
    };
  });
});
test.afterEach(({ page }) => assertNightQuiet(page));

for (const theme of ['light', 'dark'] as const)
  for (const width of [390, 1440]) {
    test(`无痕提示、独立空白输入与无障碍 ${width} ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
      await openNight(page);
      await normalReady(page);
      await enter(page);
      await expect(privateRoot(page).getByRole('region', { name: '无痕对话提示', exact: true })).toContainText(
        '这段不会被记住',
      );
      await expect(
        privateRoot(page).getByText('这段只在当前页面保留，退出无痕或刷新后会清空，不会写入长期记忆。', {
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        privateRoot(page).locator('.tool-status, .memory-receipt-actions, .receipt-action-feedback'),
      ).toHaveCount(0);
      await expect(privateRoot(page).getByRole('region', { name: '记忆记录', exact: true })).toHaveCount(0);
      await expect(privateRoot(page).getByRole('region', { name: '待确认记忆', exact: true })).toHaveCount(0);
      await auditNight(page);
      await captureNight(page, `02-private-empty-${width}-${theme}`);
      await exit(page).click();
      await expect(privateRoot(page)).toHaveCount(0);
      await expect(privacySwitch(page)).not.toBeChecked();
      await captureNight(page, `02-private-exited-${width}-${theme}`);
    });
  }

test('普通草稿附图保留；无痕发送不落存储，退出再进为空且换会话', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openNight(page);
  await normalReady(page);
  const ordinaryDraft = '普通草稿保留标记 NORMAL_DRAFT_02';
  const secret = '无痕发送检查 PRIVATE_SENT_02';
  await input(page).fill(ordinaryDraft);
  await attach(page, ordinaryImage, 'ordinary-draft.png');
  const firstId = await enter(page);
  await input(page).fill(secret);
  await attach(page, privateImage, 'private-only.png');
  await assertUnstored(page, secret, imageUrl(privateImage), privateImage.toString('base64'), firstId!);
  await page.getByRole('button', { name: '发送', exact: true }).click();
  const privateMessage = privateRoot(page).getByRole('article', { name: '你说的', exact: true });
  await expect(privateMessage).toContainText(secret);
  await expect(privateMessage.getByRole('img', { name: '本轮附图1', exact: true })).toHaveAttribute(
    'src',
    imageUrl(privateImage),
  );
  await expect(page.getByRole('button', { name: '停止回答', exact: true })).toHaveCount(0);
  await assertUnstored(page, secret, imageUrl(privateImage), privateImage.toString('base64'), firstId!);
  await captureNight(page, '02-private-sent-390');
  await exit(page).click();
  await expect(input(page)).toHaveValue(ordinaryDraft);
  await expect(attachments(page).locator('img')).toHaveAttribute('src', imageUrl(ordinaryImage));
  await expect(page.getByText(secret, { exact: true })).toHaveCount(0);
  await expect(page.locator(`img[src="${imageUrl(privateImage)}"]`)).toHaveCount(0);
  await captureNight(page, '02-ordinary-restored-390');
  const nextId = await enter(page);
  expect(nextId).not.toBe(firstId);
  await expect(privateRoot(page).getByRole('article', { name: '你说的', exact: true })).toHaveCount(0);
  await assertUnstored(page, secret, imageUrl(privateImage), privateImage.toString('base64'), firstId!, nextId!);
});

test('跨页面保留当前无痕会话，暂停页退出后恢复普通草稿附图', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openNight(page);
  await normalReady(page);
  await input(page).fill('普通跨页面草稿 NORMAL_ROUTE_02');
  await attach(page, ordinaryImage, 'ordinary-route.png');
  const id = await enter(page);
  const secret = '无痕跨页面草稿 PRIVATE_ROUTE_02';
  await input(page).fill(secret);
  await attach(page, privateImage, 'private-route.png');
  await input(page).blur();
  const nav = page.getByRole('navigation', { name: '底部导航', exact: true });
  await nav.getByRole('link', { name: '我', exact: true }).click();
  await expect(page).toHaveURL(/#\/me$/);
  await expect(page.getByText('无痕对话已暂停。', { exact: true })).toBeVisible();
  await expect(privateRoot(page)).toHaveCount(0);
  await expect(input(page)).toHaveCount(0);
  await expect(page.getByText(secret, { exact: true })).toHaveCount(0);
  await auditNight(page);
  await captureNight(page, '02-private-paused-me-390');
  await page.getByRole('link', { name: '返回无痕对话', exact: true }).click();
  await expect(privateRoot(page)).toHaveAttribute('data-thread-id', id!);
  await expect(input(page)).toHaveValue(secret);
  await expect(attachments(page).locator('img')).toHaveAttribute('src', imageUrl(privateImage));
  await nav.getByRole('link', { name: '我', exact: true }).click();
  await exit(page).click();
  await expect(page.getByText('无痕对话已暂停。', { exact: true })).toHaveCount(0);
  await nav.getByRole('link', { name: '对话', exact: true }).click();
  await expect(input(page)).toHaveValue('普通跨页面草稿 NORMAL_ROUTE_02');
  await expect(attachments(page).locator('img')).toHaveAttribute('src', imageUrl(ordinaryImage));
  await assertUnstored(page, secret, imageUrl(privateImage), privateImage.toString('base64'), id!);
});

test('刷新不会复原无痕文字、附图、线程或模式', async ({ page }) => {
  await openNight(page);
  await normalReady(page);
  const id = await enter(page),
    secret = '刷新丢弃标记 PRIVATE_RELOAD_02';
  await input(page).fill(secret);
  await attach(page, privateImage, 'private-refresh.png');
  await assertUnstored(page, secret, imageUrl(privateImage), privateImage.toString('base64'), id!);
  await page.reload();
  await normalReady(page);
  await expect(privateRoot(page)).toHaveCount(0);
  await expect(privacySwitch(page)).not.toBeChecked();
  await expect(input(page)).toHaveValue('');
  await expect(attachments(page)).toHaveCount(0);
  await assertUnstored(page, secret, imageUrl(privateImage), privateImage.toString('base64'), id!);
  const next = await enter(page);
  expect(next).not.toBe(id);
  await expect(privateRoot(page).getByRole('article')).toHaveCount(0);
  await captureNight(page, '02-private-after-reload-1440');
});

for (const host of ['browser', 'feishu'] as const) {
  test.describe(`${host} 手机浏览器仿真（非飞书真机验收）`, () => {
    test.use(
      host === 'feishu'
        ? {
            userAgent:
              'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Feishu/7.35.5',
          }
        : {},
    );
    test('安全区与VisualViewport键盘偏移下开关和退出可达', async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await installViewportSimulation(page);
      const session = await safeArea(page, 34);
      try {
        await openNight(page);
        await normalReady(page);
        if (host === 'feishu') {
          await expect(page.locator('.shell')).toHaveAttribute('data-host', 'feishu');
          await expect(page.locator('.topbar')).toBeHidden();
        }
        await reachable(privacySwitch(page), 0, 810);
        await enter(page);
        await input(page).fill('仅用于键盘仿真的无痕草稿 PRIVATE_VIEWPORT_02');
        await patchViewport(page, { height: 420, offsetTop: 0, scale: 1 });
        await input(page).focus();
        await expect(page.locator('.shell')).toHaveAttribute('data-keyboard', 'open');
        await reachable(exit(page), 0, 420);
        await expect
          .poll(async () => {
            const box = (await input(page).boundingBox())!;
            return box.y + box.height;
          })
          .toBeLessThanOrEqual(420);
        await expect(page.getByRole('navigation', { name: '底部导航', exact: true })).toBeHidden();
        await captureNight(page, `02-private-${host}-keyboard420`);
        await patchViewport(page, { height: 420, offsetTop: 120, scale: 1 });
        await expect.poll(async () => (await page.locator('.shell').boundingBox())!.y).toBeCloseTo(120, 0);
        await reachable(exit(page), 120, 540);
        await expect
          .poll(async () => {
            const box = (await input(page).boundingBox())!;
            return box.y + box.height;
          })
          .toBeLessThanOrEqual(540);
        await auditNight(page);
        await captureNight(page, `02-private-${host}-keyboard420-offset120`);
        await exit(page).click();
        await patchViewport(page, { height: 844, offsetTop: 0, scale: 1 });
        await expect(privateRoot(page)).toHaveCount(0);
        await expect(page.locator('.shell')).not.toHaveAttribute('data-keyboard');
        await expect(input(page)).toHaveValue('');
        await reachable(privacySwitch(page), 0, 810);
        await assertUnstored(page, 'PRIVATE_VIEWPORT_02');
        await captureNight(page, `02-private-${host}-keyboard-exited`);
      } finally {
        await session.detach();
      }
    });
  });
}
