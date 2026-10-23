import { expect, test, type Page } from '@playwright/test';
import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { inspectQ9, assertQ9Inspection } from './q9-night-helpers';

const runId = process.env.MINGJING_Q9_RUN_ID!;
const output = path.resolve(`evidence/2026-10-21/Q9/static/${runId}`);
const states = [
  ...['today', 'chat', 'chart', 'tarot', 'cases', 'me', 'settings', '__design'].map((id) => ({
    id,
    mode: 'static',
    url: `/?preview=1#/${id}`,
    prepare: 'page',
  })),
  ...['bazi', 'ziwei', 'astro'].map((id) => ({
    id: `chart-${id}`,
    mode: 'components',
    url: `/?components=demo#/chart?tab=${id}`,
    prepare: 'chart',
  })),
  ...['focus1', 'reflect3', 'choice5'].map((id) => ({
    id: `tarot-${id}`,
    mode: 'components',
    url: `/?components=demo#/tarot?spread=${id}&step=reveal`,
    prepare: 'reveal',
  })),
  {
    id: 'tarot-picker',
    mode: 'components',
    url: '/?components=demo#/tarot?spread=reflect3&step=pick',
    prepare: 'picker',
  },
  { id: 'calendar', mode: 'components', url: '/?components=demo#/today', prepare: 'calendar' },
];
const viewports = [
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
];
const sha = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');
async function prepare(page: Page, state: (typeof states)[number]) {
  await page.goto(state.url, { waitUntil: 'domcontentloaded' });
  const pageName =
    state.mode === 'static'
      ? state.id
      : state.prepare === 'chart'
        ? 'chart'
        : state.prepare === 'calendar'
          ? 'today'
          : 'tarot';
  await expect(page.locator(`[data-page="${pageName}"]`)).toBeVisible();
  if (state.prepare === 'calendar' && page.viewportSize()!.width < 1024) {
    await page.getByRole('button', { name: '查看本月日历', exact: true }).click();
    await expect(page.getByRole('dialog', { name: '本月日历', exact: true })).toBeVisible();
  }
  if (state.prepare === 'reveal') {
    await page.getByRole('button', { name: '全部揭开', exact: true }).click();
    const count = state.id.endsWith('focus1') ? 1 : state.id.endsWith('reflect3') ? 3 : 5;
    await expect(page.locator('.tarot-flip-front')).toHaveCount(count);
  }
  if (state.prepare === 'picker') {
    const picker = page.getByRole('group', { name: '亲手点选牌背', exact: true });
    await expect(picker).toBeVisible();
    await expect(picker.getByRole('button')).toHaveCount(78);
  }
  if (state.prepare === 'chart') {
    await expect(page.getByRole('group', { name: '命盘体系' }).getByRole('button', { pressed: true })).toHaveText(
      ({ 'chart-bazi': '八字', 'chart-ziwei': '紫微', 'chart-astro': '星盘' } as Record<string, string>)[state.id]!,
    );
  }
  await page.evaluate(() => document.fonts.ready);
  await page.waitForLoadState('networkidle');
}

test.beforeAll(async () => {
  await fs.mkdir(output, { recursive: true });
  const header = {
    run_id: runId,
    invocation: process.env.MINGJING_Q9_STATIC_INVOCATION,
    expected: states.length * 8,
    synthetic_only: true,
  };
  const filename = path.join(output, 'run.json');
  try {
    await fs.writeFile(filename, JSON.stringify(header) + '\n', { flag: 'wx' });
  } catch (error) {
    if (!(error instanceof Error) || !('code' in error) || error.code !== 'EEXIST') throw error;
    const existing = JSON.parse(await fs.readFile(filename, 'utf8')) as Record<string, unknown>;
    if (existing.invocation !== header.invocation || existing.run_id !== runId)
      throw new Error('Visual evidence belongs to another invocation');
  }
});

for (const viewport of viewports)
  for (const theme of ['light', 'dark'])
    for (const state of states) {
      test(`${state.mode} ${state.id} ${theme} ${viewport.width}`, async ({ page }) => {
        await page.setViewportSize(viewport);
        await page.clock.setFixedTime(new Date('2026-10-21T07:15:00+08:00'));
        await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
        const activity = {
          api: [] as string[],
          external: [] as string[],
          errors: [] as string[],
          console: [] as string[],
        };
        page.on('request', (request) => {
          const url = new URL(request.url());
          if (url.pathname.startsWith('/api/')) activity.api.push(url.pathname);
          if (['http:', 'https:'].includes(url.protocol) && url.origin !== 'http://127.0.0.1:4173')
            activity.external.push(url.origin);
        });
        page.on('pageerror', (error) => activity.errors.push(error.message));
        page.on('console', (message) => activity.console.push(`${message.type()}: ${message.text()}`));
        await page.route('**/*', async (route) => {
          const url = new URL(route.request().url());
          if (
            url.pathname.startsWith('/api/') ||
            (['http:', 'https:'].includes(url.protocol) && url.origin !== 'http://127.0.0.1:4173')
          )
            return route.abort();
          return route.continue();
        });
        await prepare(page, state);
        const inspection = await inspectQ9(page);
        const filename = `${state.mode}-${state.id}-${theme}-${viewport.width}`;
        const image = await page.screenshot({ fullPage: true, animations: 'disabled' });
        const audit = {
          run_id: runId,
          id: state.id,
          mode: state.mode,
          viewport,
          theme,
          url: state.url,
          screenshot: `web/${path.relative(process.cwd(), path.join(output, filename + '.png')).replaceAll('\\', '/')}`,
          sha256: sha(image),
          synthetic_only: true,
          checks: inspection,
          activity,
        };
        await fs.writeFile(path.join(output, filename + '.png'), image, { flag: 'wx' });
        await fs.writeFile(path.join(output, filename + '.json'), JSON.stringify(audit, null, 2) + '\n', {
          flag: 'wx',
        });
        assertQ9Inspection(inspection, theme);
        expect(activity).toEqual({ api: [], external: [], errors: [], console: [] });
      });
    }
