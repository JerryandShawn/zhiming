import { expect, type Page } from '@playwright/test';
import fs from 'node:fs/promises';
import AxeBuilder from '@axe-core/playwright';
import { cinnabarUsages } from './appearance';

type Activity = { api: string[]; external: string[]; errors: string[]; console: string[] };
const activities = new WeakMap<Page, Activity>();
export function guardNight(page: Page) {
  const activity: Activity = { api: [], external: [], errors: [], console: [] };
  activities.set(page, activity);
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (/^\/api(?:\/|$)/.test(url.pathname)) activity.api.push(url.pathname);
    if (['http:', 'https:'].includes(url.protocol) && url.origin !== 'http://127.0.0.1:4173')
      activity.external.push(url.origin);
  });
  page.on('pageerror', (error) => activity.errors.push(error.message));
  page.on('console', (message) => activity.console.push(`${message.type()}: ${message.text()}`));
}
export function assertNightQuiet(page: Page) {
  expect(activities.get(page)).toEqual({ api: [], external: [], errors: [], console: [] });
}
export async function openNight(page: Page, route = 'chat') {
  await page.goto(`/?night=demo#/${route}`);
  await expect(page.getByRole('complementary', { name: '本地演示说明' })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}
export async function captureNight(page: Page, name: string, fullPage = false) {
  if (process.env.NIGHT_CAPTURE_ONLY && !name.startsWith(process.env.NIGHT_CAPTURE_ONLY)) return;
  const directory = process.env.NIGHT_EVIDENCE_DIR || 'evidence/2026-10-19';
  await fs.mkdir(directory, { recursive: true });
  await page.screenshot({ path: `${directory}/${name}.png`, fullPage, animations: 'disabled' });
}
export async function auditNight(page: Page) {
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  const accents = await page.evaluate(cinnabarUsages);
  expect(accents.length, JSON.stringify(accents)).toBeLessThanOrEqual(3);
}
