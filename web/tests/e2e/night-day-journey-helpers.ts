import { expect, type Page, type TestInfo } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { assertNightQuiet, auditNight, guardNight } from './night-helpers';

const origin = 'http://127.0.0.1:4173';
const activity = new WeakMap<Page, { writes: string[]; documents: string[] }>();
export const today = (page: Page) => page.locator('[data-runtime="night-today"]');
export const chat = (page: Page) => page.locator('[data-page="chat"][data-scenario]');
export const me = (page: Page) => page.locator('[data-runtime="night-me"]');
export const settings = (page: Page) => page.locator('[data-runtime="night-settings"]');
export const composer = (page: Page) => chat(page).getByRole('textbox', { name: '和明镜说说', exact: true });
export const followup = (page: Page) => today(page).locator('[data-plan-id="demo-followup-today"]');
export const morning = (page: Page) => settings(page).locator('[data-report-kind="daily"]');
export const contact = (page: Page) => settings(page).getByRole('region', { name: '主动联系', exact: true });
export const healthText = '希望跟进一项健康安排（合成示例）';
export const healthMemory = (page: Page) => me(page).locator('[data-memory-id]').filter({ hasText: healthText });
export const healthReceipt = (page: Page) =>
  chat(page).getByRole('group', { name: '记忆记录', exact: true }).filter({ hasText: healthText });

export async function revealDayReceipts(page: Page) {
  const disclosure = chat(page).locator('.receipt-group > details');
  const summary = disclosure.locator(':scope > summary');
  await expect(summary).toContainText('记下了 2 件事');
  if (!(await disclosure.evaluate((element) => (element as HTMLDetailsElement).open))) await summary.click();
  await expect(healthReceipt(page)).toBeVisible();
}

export async function setBeijingClock(page: Page, time: '08:00' | '12:00' | '22:00') {
  await page.clock.setFixedTime(new Date(`2026-10-21T${time}:00+08:00`));
  expect(
    await page.evaluate(() =>
      new Intl.DateTimeFormat('en-GB', {
        timeZone: 'Asia/Shanghai',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23',
      }).format(new Date()),
    ),
  ).toBe(time);
}

export async function prepareDayJourney(page: Page) {
  guardNight(page);
  const log = { writes: [] as string[], documents: [] as string[] };
  activity.set(page, log);
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (!['http:', 'https:'].includes(url.protocol)) return;
    if (request.method() !== 'GET') log.writes.push(`${request.method()} ${url.pathname}`);
    if (request.resourceType() === 'document') log.documents.push(request.url());
  });
  await page.route('**/*', async (route) => {
    const request = route.request(),
      url = new URL(request.url());
    if (
      ['http:', 'https:'].includes(url.protocol) &&
      (request.method() !== 'GET' ||
        url.origin !== origin ||
        /^\/(?:api|__test__|__frontend_fixture__)(?:\/|$)/.test(url.pathname))
    )
      await route.abort();
    else await route.continue();
  });
  await setBeijingClock(page, '08:00');
}

export function assertDayJourneyQuiet(page: Page) {
  assertNightQuiet(page);
  const log = activity.get(page);
  expect(log?.writes, 'No real transport writes are allowed').toEqual([]);
  expect(log?.documents, 'The journey must use one document; no refresh or entry-mode change').toHaveLength(1);
  expect(new URL(page.url()).search).toBe('?night=demo');
  expect(page.context().pages()).toHaveLength(1);
}

export async function navigateDayJourney(page: Page, width: number, name: '今日' | '对话' | '关于我') {
  const navigation = page.locator(width < 1024 ? '.tabbar' : '.rail');
  const visibleName = width < 1024 && name === '关于我' ? '我' : name;
  await navigation.getByRole('link', { name: visibleName, exact: true }).click();
  const target = name === '今日' ? today(page) : name === '对话' ? chat(page) : me(page);
  await expect(target).toBeVisible();
  assertDayJourneyQuiet(page);
}

export async function meTab(page: Page, name: '画像' | '记忆' | '待确认') {
  await me(page)
    .getByRole('group', { name: '关于我的分区', exact: true })
    .getByRole('button', { name, exact: true })
    .click();
}

async function atDocumentTop(page: Page) {
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect.poll(() => page.evaluate(() => ({ x: scrollX, y: scrollY }))).toEqual({ x: 0, y: 0 });
}

async function assertDayViewportShell(page: Page) {
  const viewport = page.viewportSize();
  if (!viewport) throw new Error('A fixed viewport is required for shell geometry evidence');
  const mobile = viewport.width < 1024;
  const shell = page.locator(mobile ? '.tabbar' : '.rail');
  await expect(shell).toBeVisible();
  const geometry = await shell.evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    return {
      position: getComputedStyle(element).position,
      left: bounds.left,
      top: bounds.top,
      bottom: bounds.bottom,
      width: bounds.width,
      height: bounds.height,
      viewportHeight: innerHeight,
      viewportWidth: innerWidth,
    };
  });
  expect(geometry.viewportWidth).toBe(viewport.width);
  expect(geometry.viewportHeight).toBe(viewport.height);
  expect(geometry.position).toBe(mobile ? 'fixed' : 'sticky');
  expect(Math.abs(geometry.left)).toBeLessThanOrEqual(1);
  expect(Math.abs(geometry.bottom - viewport.height)).toBeLessThanOrEqual(1);
  expect(geometry.height).toBeGreaterThan(0);
  if (mobile) {
    expect(Math.abs(geometry.width - viewport.width)).toBeLessThanOrEqual(1);
    expect(geometry.top).toBeGreaterThanOrEqual(0);
    expect(geometry.height).toBeLessThan(viewport.height);
  } else {
    expect(Math.abs(geometry.top)).toBeLessThanOrEqual(1);
    expect(Math.abs(geometry.height - viewport.height)).toBeLessThanOrEqual(1);
    expect(geometry.width).toBeGreaterThan(0);
    expect(geometry.width).toBeLessThan(viewport.width);
  }
}

export async function dayCheckpoint(page: Page, name: string, info: TestInfo, options: { viewport?: boolean } = {}) {
  await page.evaluate(() => document.fonts.ready);
  await atDocumentTop(page);
  await auditNight(page); // All Axe rules; cinnabar <=3 under the approved viewport exclusions.
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await assertDayViewportShell(page);
  assertDayJourneyQuiet(page);
  const directory =
    process.env.JOURNEY_EVIDENCE_DIR ?? process.env.NIGHT_EVIDENCE_DIR ?? 'evidence/2026-10-21/day-journey';
  await fs.mkdir(directory, { recursive: true });
  const filename = path.join(directory, `${name}-${randomUUID().slice(0, 8)}.png`);
  await fs.writeFile(filename, await page.screenshot({ fullPage: true, animations: 'disabled' }), { flag: 'wx' });
  info.annotations.push({ type: 'day_journey_screenshot', description: filename.replaceAll('\\', '/') });
  if (options.viewport) {
    // A full-page image cannot prove fixed/sticky viewport placement. Capture
    // the normal viewport separately after its geometry has been rechecked.
    await atDocumentTop(page);
    await assertDayViewportShell(page);
    await auditNight(page);
    assertDayJourneyQuiet(page);
    const viewportFilename = path.join(directory, `${name}-viewport-${randomUUID().slice(0, 8)}.png`);
    await fs.writeFile(viewportFilename, await page.screenshot({ fullPage: false, animations: 'disabled' }), {
      flag: 'wx',
    });
    info.annotations.push({
      type: 'day_journey_viewport_screenshot',
      description: viewportFilename.replaceAll('\\', '/'),
    });
  }
}
