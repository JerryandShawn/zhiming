import { expect, type Page } from '@playwright/test';
import fs from 'node:fs/promises';

export const componentEvidence = 'evidence/2026-10-18/components-m5';
type Activity = { api: string[]; external: string[]; errors: string[]; console: string[] };
const activities = new WeakMap<Page, Activity>();
export function guardDemo(page: Page) {
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
  return activity;
}
export function demoActivity(page: Page) {
  return activities.get(page)!;
}
export function assertDemoQuiet(page: Page) {
  expect(demoActivity(page)).toEqual({ api: [], external: [], errors: [], console: [] });
}
export async function openDemo(page: Page, route: string) {
  await page.goto(`/?components=demo#/${route}`);
  await expect(page.getByRole('region', { name: '组件模拟说明' })).toBeVisible();
  await expect(page.locator('[data-page]')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}
export async function captureComponent(page: Page, name: string, fullPage = false) {
  const directory = `${componentEvidence}/interactions`;
  await fs.mkdir(directory, { recursive: true });
  if (fullPage) await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${directory}/${name}.png`, fullPage, animations: 'disabled' });
}
