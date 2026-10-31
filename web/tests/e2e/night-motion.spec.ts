import { expect, test } from '@playwright/test';
import { prepareMotion, motionLog, openStaticProfile, assertMotionQuiet, noActiveDialog } from './motion-helpers';
import { installViewportSimulation, patchViewport, safeArea } from './components-embed-helpers';

test.use({ reducedMotion: 'no-preference', timezoneId: 'Asia/Shanghai' });

for (const width of [390, 1440]) {
  for (const dismissal of ['Escape', '关闭']) {
    test(`正常Sheet入240出180，焦点与同URL历史保留 ${width} ${dismissal}`, async ({ page }) => {
      await prepareMotion(page, width);
      const trigger = await openStaticProfile(page);
      await trigger.click();
      const dialog = page.getByRole('dialog', { name: '修改画像条目', exact: true });
      await expect(dialog).toBeVisible();
      await expect
        .poll(
          async () =>
            (await motionLog(page)).css.filter((entry) => entry.target.includes('sheet') && entry.state === 'open')
              .length,
        )
        .toBeGreaterThan(0);
      const opened = (await motionLog(page)).css.find(
        (entry) => entry.target.includes('sheet') && entry.state === 'open',
      )!;
      expect(opened.duration).toBe('0.24s');
      expect(opened.name).toBe(width === 390 ? 'sheet-enter' : 'drawer-enter');
      if (dismissal === 'Escape') await page.keyboard.press('Escape');
      else await dialog.getByRole('button', { name: '关闭', exact: true }).click();
      await noActiveDialog(page);
      const closed = (await motionLog(page)).css.find(
        (entry) => entry.target.includes('sheet') && entry.state === 'closed',
      );
      expect(closed).toMatchObject({ duration: '0.18s', name: width === 390 ? 'sheet-exit' : 'drawer-exit' });
      await expect(trigger).toBeFocused();
      expect((await motionLog(page)).routes).toHaveLength(1);
      await assertMotionQuiet(page, `Q8-sheet-closed-${width}-${dismissal}`);
      await page.goBack();
      await expect(page).toHaveURL(/#\/today$/);
    });
  }

  test(`运行中改为减少动效：开与关均无残留遮罩 ${width}`, async ({ page }) => {
    await prepareMotion(page, width);
    const trigger = await openStaticProfile(page);
    await trigger.click();
    await page.emulateMedia({ reducedMotion: 'reduce' });
    let dialog = page.getByRole('dialog', { name: '修改画像条目', exact: true });
    await expect(dialog).toBeVisible();
    const durations = await dialog.evaluate((node) => ({
      animation: getComputedStyle(node).animationDuration,
      delay: getComputedStyle(node).animationDelay,
    }));
    expect(durations).toEqual({ animation: '0s', delay: '0s' });
    await page.keyboard.press('Escape');
    await noActiveDialog(page);
    await expect(trigger).toBeFocused();
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await trigger.click();
    dialog = page.getByRole('dialog', { name: '修改画像条目', exact: true });
    await expect(dialog).toBeVisible();
    // Stretch only the test exit so the preference change is guaranteed to occur mid-exit.
    // The preceding tests independently enforce the product's actual180ms duration.
    await page.addStyleTag({ content: '.dialog.sheet[data-state="closed"]{animation-duration:5s}' });
    await page.keyboard.press('Escape');
    await expect(page.locator('.dialog[data-state="closed"]')).toBeAttached();
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await noActiveDialog(page);
    await expect(trigger).toBeFocused();
    await assertMotionQuiet(page, `Q8-dynamic-reduced-motion-${width}`);
  });
}

test('已加载的延迟Sheet关闭仍有退场，快速重开不被旧动画结束关闭', async ({ page }) => {
  await prepareMotion(page, 390);
  await page.goto('/?preview=1#/chat');
  const trigger = page.getByRole('button', { name: '更多页面', exact: true });
  await trigger.click();
  let dialog = page.getByRole('dialog', { name: '去哪里看看', exact: true });
  await expect(dialog).toBeVisible();
  await page.keyboard.press('Escape');
  await noActiveDialog(page);
  expect((await motionLog(page)).css.some((entry) => entry.target.includes('sheet') && entry.state === 'closed')).toBe(
    true,
  );
  await trigger.click();
  dialog = page.getByRole('dialog', { name: '去哪里看看', exact: true });
  await expect(dialog).toBeVisible();
  await page.keyboard.press('Escape');
  await trigger.evaluate((node) => {
    if (!(node instanceof HTMLButtonElement)) throw new Error('Expected the stable panel button');
    node.click();
  });
  await expect(dialog).toHaveAttribute('data-state', 'open');
  await dialog.evaluate((node) =>
    node.dispatchEvent(new AnimationEvent('animationend', { animationName: 'sheet-exit', bubbles: true })),
  );
  await expect(dialog).toBeVisible();
  await page.keyboard.press('Escape');
  await noActiveDialog(page);
  await expect(trigger).toBeFocused();
  await page.goForward();
  await noActiveDialog(page);
  await assertMotionQuiet(page, 'Q8-deferred-rapid-reopen-390');
});

test('切页只淡入当前内容，减少动效立即取消且不重放首次动画', async ({ page }) => {
  await prepareMotion(page, 390);
  await page.goto('/?preview=1#/today');
  await expect(page.locator('[data-page="today"]')).toBeVisible();
  expect((await motionLog(page)).routes).toEqual([]);
  await page.evaluate(() => {
    location.hash = '#/chat';
  });
  await expect(page.locator('[data-page="chat"]')).toBeVisible();
  await expect.poll(async () => (await motionLog(page)).routes.length).toBe(1);
  const record = (await motionLog(page)).routes[0];
  expect(record.duration).toBe(120);
  expect(
    record.keyframes.every((frame) => typeof frame === 'object' && frame !== null && !('transform' in frame)),
  ).toBe(true);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  expect(
    await page
      .locator('#main')
      .evaluate((node) => node.getAnimations().filter((animation) => animation.playState === 'running').length),
  ).toBe(0);
  await page.evaluate(() => {
    location.hash = '#/settings';
  });
  await expect(page.locator('[data-page="settings"]')).toBeVisible();
  expect((await motionLog(page)).routes).toHaveLength(1);
  await expect(page.locator('[data-page="chat"]')).toHaveCount(0);
  await assertMotionQuiet(page, 'Q8-route-reduced-current-only-390');
});

for (const mode of ['preview', 'night']) {
  test(`冷路由等待时旧对话DOM已移除，控制器与普通草稿仍保留 ${mode}`, async ({ page }) => {
    await prepareMotion(page, 390);
    let seen!: () => void, release!: () => void;
    const requested = new Promise<void>((resolve) => {
      seen = resolve;
    });
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route(mode === 'night' ? '**/assets/SettingsPage-*.js' : '**/assets/Settings-*.js', async (route) => {
      seen();
      await gate;
      await route.continue();
    });
    await page.goto(mode === 'night' ? '/?night=demo#/chat' : '/?preview=1#/chat');
    const chat = page.locator('[data-page="chat"]');
    await expect(chat).toBeVisible();
    if (mode === 'night') await expect(chat).toHaveAttribute('data-complete', 'true');
    const input = page.getByRole('textbox', { name: '和明镜说说', exact: true });
    const draft = '冷路由后仍保留的普通合成草稿';
    if (mode === 'night') await input.fill(draft);
    await page.evaluate(() => {
      location.hash = '#/settings';
    });
    try {
      await requested;
      await expect(page.getByRole('status', { name: '正在展开页面', exact: true })).toBeVisible();
      await expect(chat).toHaveCount(0);
      await assertMotionQuiet(page, `Q8-cold-route-loading-${mode}-390`);
    } finally {
      release();
    }
    await expect(page.locator('[data-page="settings"]')).toBeVisible();
    await page.evaluate(() => {
      location.hash = '#/chat';
    });
    await expect(chat).toBeVisible();
    if (mode === 'night') await expect(input).toHaveValue(draft);
    await assertMotionQuiet(page, `Q8-cold-route-returned-${mode}-390`);
  });
}

test('键盘420偏移120与两侧安全区44下Sheet不移出可视区域', async ({ page }) => {
  await prepareMotion(page, 390);
  await installViewportSimulation(page);
  await safeArea(page, 34, 44);
  const trigger = await openStaticProfile(page);
  await trigger.click();
  const dialog = page.getByRole('dialog', { name: '修改画像条目', exact: true });
  await expect(dialog).toBeVisible();
  await patchViewport(page, { height: 420, offsetTop: 120, scale: 1 });
  await dialog.getByRole('textbox', { name: '你的说法', exact: true }).focus();
  await expect(page.locator('html')).toHaveAttribute('data-visual-keyboard', 'open');
  const box = (await dialog.boundingBox())!;
  expect(box.y).toBeGreaterThanOrEqual(120);
  expect(box.y + box.height).toBeLessThanOrEqual(541);
  const close = (await dialog.getByRole('button', { name: '关闭', exact: true }).boundingBox())!;
  expect(close.x).toBeGreaterThanOrEqual(44);
  expect(close.x + close.width).toBeLessThanOrEqual(346);
  expect(await dialog.evaluate((node) => getComputedStyle(node).animationDuration)).toBe('0s');
  await assertMotionQuiet(page, 'Q8-sheet-keyboard420-offset120-safe44-390');
  await page.keyboard.press('Escape');
  await noActiveDialog(page);
  await expect(trigger).toBeFocused();
});
