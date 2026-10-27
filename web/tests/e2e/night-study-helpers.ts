import { expect, type Locator, type Page, type TestInfo } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { assertNightQuiet, auditNight, guardNight } from './night-helpers';

const origin = 'http://127.0.0.1:4173';
const route = '/?spaces=demo#/chat?space=study&topic=chart-study';
const requests = new WeakMap<Page, { writes: string[]; study: string[] }>();
export const workspace = (page: Page) => page.locator('[data-runtime="study-workspace"]');
export const dictionary = (page: Page) => workspace(page).getByRole('region', { name: '术语词典', exact: true });
export const learning = (page: Page) => workspace(page).getByRole('region', { name: '学习卡', exact: true });
export const composer = (page: Page) => page.getByRole('textbox', { name: '本地对话草稿', exact: true });
export const rows = (page: Page) => dictionary(page).getByRole('list', { name: '术语检索结果', exact: true });
export const studyUrl = route;

export async function prepareStudy(page: Page) {
  guardNight(page);
  const activity = { writes: [] as string[], study: [] as string[] };
  requests.set(page, activity);
  await page.clock.setFixedTime(new Date('2026-10-21T09:15:00+08:00'));
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (!['http:', 'https:'].includes(url.protocol)) return;
    if (request.method() !== 'GET') activity.writes.push(`${request.method()} ${url.pathname}`);
    if (url.pathname.startsWith('/data/study/')) activity.study.push(url.pathname);
  });
  await page.route('**/*', async (request) => {
    const value = request.request();
    const url = new URL(value.url());
    if (
      ['http:', 'https:'].includes(url.protocol) &&
      (value.method() !== 'GET' ||
        url.origin !== origin ||
        /^\/(?:api|__test__|__frontend_fixture__)(?:\/|$)/.test(url.pathname))
    )
      await request.abort();
    else await request.continue();
  });
}

export function assertStudyQuiet(page: Page) {
  assertNightQuiet(page);
  expect(requests.get(page)?.writes, 'Study interactions must remain GET-only').toEqual([]);
}

export async function openStudy(page: Page, width: number, theme: string) {
  await page.setViewportSize({ width, height: width < 768 ? 844 : 900 });
  await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
  await page.goto(route);
  await expect(workspace(page)).toHaveAttribute('data-study-state', 'ready');
  await expect(workspace(page)).toContainText('212条术语 · 39处登记出处 · 15张合成学习卡');
  await page.evaluate(() => document.fonts.ready);
  // The browser reads exactly these public educational assets, never personal chart/API data.
  expect([...new Set(requests.get(page)?.study)].sort()).toEqual(
    [
      '/data/study/glossary/manifest.json',
      '/data/study/glossary/terms_v1.json',
      '/data/study/glossary/sources_v1.json',
      '/data/study/learning/manifest.json',
      '/data/study/learning/learning-ayuan-bazi.json',
      '/data/study/learning/learning-ayuan-ziwei.json',
      '/data/study/learning/learning-ayuan-astro.json',
    ].sort(),
  );
}

export async function tab(page: Page, name: '对话' | '术语词典' | '学习卡') {
  const target = workspace(page)
    .getByRole('group', { name: '命理研习视图', exact: true })
    .getByRole('button', { name, exact: true });
  await target.click();
  await expect(target).toHaveAttribute('aria-pressed', 'true');
}

export async function choose(page: Page, label: string, value: string) {
  const control = page.getByRole('combobox', { name: label, exact: true });
  await control.click();
  await page
    .getByRole('listbox', { name: label, exact: true })
    .getByRole('option', { name: value, exact: true })
    .click();
  await expect(page.getByRole('listbox', { name: label, exact: true })).toHaveCount(0);
  await expect(control).toBeFocused();
}

export async function tabTo(page: Page, target: Locator) {
  await expect(target).toBeVisible();
  for (let index = 0; index < 150; index++) {
    if (await target.evaluate((node) => node === document.activeElement)) return;
    await page.keyboard.press('Tab');
  }
  await expect(target, 'Study control must be reachable through the real Tab order').toBeFocused();
}

export async function insideDialog(page: Page, dialog: Locator) {
  await expect(dialog).toBeVisible();
  for (let index = 0; index < 6; index++) {
    await page.keyboard.press('Tab');
    expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press('Shift+Tab');
  expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
}

export async function auditStudy(page: Page) {
  await auditNight(page); // All Axe rules and the approved viewport cinnabar counting policy.
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  const dialog = page.getByRole('dialog');
  if (await dialog.count())
    expect(await dialog.evaluate((node) => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
  assertStudyQuiet(page);
}

export async function captureStudy(page: Page, name: string, info: TestInfo, outputDirectory?: string) {
  const directory =
    outputDirectory ?? process.env.STUDY_EVIDENCE_DIR ?? process.env.NIGHT_EVIDENCE_DIR ?? 'evidence/2026-10-21/study';
  await fs.mkdir(directory, { recursive: true });
  const filename = path.join(directory, `${name}-${randomUUID().slice(0, 8)}.png`);
  await page.evaluate(() => window.scrollTo(0, 0));
  const dialog = page.getByRole('dialog');
  const modal = (await dialog.count()) > 0;
  if (modal)
    await dialog.evaluate((node) => {
      node.scrollTop = 0;
    });
  await fs.writeFile(filename, await page.screenshot({ fullPage: !modal, animations: 'disabled' }), { flag: 'wx' });
  info.annotations.push({ type: 'study_screenshot', description: filename.replaceAll('\\', '/') });
}
