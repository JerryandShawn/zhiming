import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { cinnabarUsages } from './appearance';

const runId = process.env.MINGJING_OVERNIGHT_RUN_ID!;
const evidence = path.resolve('evidence/2026-10-19/07');
const states = [
  ...['today', 'chat', 'chart', 'tarot', 'cases', 'me', 'settings'].map((name) => ({
    id: `night-${name}`,
    name,
    url: `/?night=demo#/${name}`,
    mode: 'night',
  })),
  { id: 'spaces-chat', name: 'chat', url: '/?spaces=demo#/chat?space=career&topic=interview', mode: 'spaces' },
  { id: 'spaces-me', name: 'me', url: '/?spaces=demo#/me', mode: 'spaces' },
  { id: 'spaces-organize', name: 'organize', url: '/?spaces=demo#/organize', mode: 'spaces' },
  { id: 'guide', name: 'chat', url: '/?night=demo#/chat', mode: 'guide' },
];
const viewports = [
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
];
const expected = states.length * viewports.length * 2;
const hash = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');
let sourceHashes: Record<string, string> = {},
  buildHashes: Record<string, string> = {};

async function hashes(directory: string, prefix: string): Promise<Record<string, string>> {
  const entries = await fs.readdir(directory, { withFileTypes: true });
  const fragments = await Promise.all(
    entries.map(async (entry) => {
      const filename = path.join(directory, entry.name),
        key = `${prefix}/${entry.name}`;
      if (entry.isDirectory()) return hashes(filename, key);
      return /\.(tsx?|css|html|m?js|json)$/.test(entry.name) ? { [key]: hash(await fs.readFile(filename)) } : {};
    }),
  );
  return Object.assign({}, ...fragments) as Record<string, string>;
}
async function atomicJson(filename: string, value: unknown) {
  await fs.mkdir(path.dirname(filename), { recursive: true });
  const temporary = `${filename}.${process.pid}.tmp`;
  await fs.writeFile(temporary, JSON.stringify(value, null, 2) + '\n');
  await fs.rename(temporary, filename);
}
async function prepare(page: Page, item: (typeof states)[number]) {
  await page.goto(item.url, { waitUntil: 'domcontentloaded' });
  await expect(page.locator(`[data-page="${item.name}"]`)).toBeVisible({ timeout: 15000 });
  if (item.mode === 'night' && item.name === 'chat')
    await expect(page.locator('[data-complete="true"]')).toBeVisible({ timeout: 15000 });
  if (item.mode === 'night' && item.name === 'chart')
    await expect(page.locator('[data-runtime="night-chart-samples"]')).toBeVisible();
  if (item.mode === 'night' && item.name === 'me')
    await expect(page.locator('[data-runtime="night-me"]')).toBeVisible();
  if (item.mode === 'night' && item.name === 'settings')
    await expect(page.locator('[data-runtime="night-settings"]')).toBeVisible();
  if (item.mode === 'guide') {
    await page.getByRole('button', { name: '初次相识演示', exact: true }).click();
    await page.getByRole('button', { name: '开始认识', exact: true }).click();
    await expect(page.locator('[data-runtime="night-onboarding"]')).toHaveAttribute('data-step', 'user_name');
  }
  if (item.id === 'spaces-chat') await expect(page.locator('[data-message]')).toHaveCount(4);
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    document.querySelectorAll('.chat-messages').forEach((element) => {
      element.scrollTop = 0;
    });
  });
}

test.beforeAll(async () => {
  await fs.mkdir(path.join(evidence, 'screenshots'), { recursive: true });
  await fs.mkdir(path.join(evidence, 'audits'), { recursive: true });
  [sourceHashes, buildHashes] = await Promise.all([hashes('src', 'web/src'), hashes('../static/dist', 'static/dist')]);
  for (const filename of [
    'tests/e2e/overnight-matrix.spec.ts',
    'tests/e2e/appearance.ts',
    'playwright.overnight-visual.config.ts',
  ])
    sourceHashes[`web/${filename}`] = hash(await fs.readFile(filename));
});

test.afterAll(async ({ browserName }, info) => {
  const names = (await fs.readdir(path.join(evidence, 'audits'))).filter((name) => name.endsWith('.json'));
  const audits = (
    await Promise.all(
      names.map(
        async (name) =>
          JSON.parse(await fs.readFile(path.join(evidence, 'audits', name), 'utf8')) as Record<string, unknown>,
      ),
    )
  ).filter((audit) => audit.run_id === runId);
  const metadata = {
    schema: 'night-whole-site-visual-v1',
    browser_name: browserName,
    run_id: runId,
    synthetic_only: true,
    backend_required: false,
    expected_combinations: expected,
    captured_combinations: audits.length,
    source_hashes: sourceHashes,
    build_hashes: buildHashes,
    capture_scope:
      'Base page state; chat captures the visible internal scroll viewport. Other interaction states have 01–06 evidence.',
    reference_counting: '14 I.6: content emphasis only; brand, selected navigation and semantic chart colors excluded.',
    captures: audits,
  };
  // Per-case files appear only after their complete atomic write. The last worker writes the complete manifest.
  await atomicJson(path.join(evidence, `worker-${info.workerIndex}.json`), metadata);
  if (audits.length === expected) await atomicJson(path.join(evidence, 'manifest.json'), metadata);
});

for (const viewport of viewports)
  for (const theme of ['light', 'dark'])
    for (const item of states) {
      test(`${item.id} ${theme} ${viewport.width}`, async ({ page }) => {
        await page.setViewportSize(viewport);
        await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
        const activity = {
          api: [] as string[],
          external: [] as string[],
          errors: [] as string[],
          console: [] as string[],
        };
        page.on('request', (request) => {
          const url = new URL(request.url());
          if (/^\/api(?:\/|$)/.test(url.pathname)) activity.api.push(`${request.method()} ${url.pathname}`);
          if (['http:', 'https:'].includes(url.protocol) && url.origin !== 'http://127.0.0.1:4173')
            activity.external.push(url.origin);
        });
        page.on('pageerror', (error) => activity.errors.push(error.message));
        page.on('console', (message) => activity.console.push(`${message.type()}: ${message.text()}`));
        await page.route('**/*', async (route) => {
          const url = new URL(route.request().url());
          if (
            /^\/api(?:\/|$)/.test(url.pathname) ||
            (['http:', 'https:'].includes(url.protocol) && url.origin !== 'http://127.0.0.1:4173')
          )
            await route.abort();
          else await route.continue();
        });
        let readinessError = '';
        try {
          await prepare(page, item);
        } catch (reason) {
          readinessError = reason instanceof Error ? reason.message : '页面尚未就绪';
        }
        const visual = await page.evaluate(() => ({
          overflow: document.documentElement.scrollWidth > innerWidth,
          font_faces: document.fonts.size,
          rendered_theme: document.documentElement.dataset.theme,
          small_text: Array.from(document.querySelectorAll('main *'))
            .filter((element) => {
              if (!(element instanceof HTMLElement)) return false;
              const style = getComputedStyle(element),
                rect = element.getBoundingClientRect();
              return (
                rect.width > 0 &&
                rect.height > 0 &&
                style.display !== 'none' &&
                style.visibility !== 'hidden' &&
                Array.from(element.childNodes).some((node) => node.nodeType === 3 && node.textContent?.trim()) &&
                parseFloat(style.fontSize) < 13 &&
                !element.closest('.citation, .calendar-mark, .calendar-festival')
              );
            })
            .map((element) => element.className),
        }));
        const accents = await page.evaluate(cinnabarUsages);
        const filename = `${item.id}-${theme}-${viewport.width}`;
        const screenshot = path.join(evidence, 'screenshots', `${filename}.png`);
        await page.screenshot({ path: screenshot, fullPage: true, animations: 'disabled' });
        let axeError = '';
        let violations: unknown[] = [];
        try {
          violations = (await new AxeBuilder({ page }).analyze()).violations.map((violation) => ({
            id: violation.id,
            impact: violation.impact,
            nodes: violation.nodes.map((node) => ({ target: node.target, summary: node.failureSummary })),
          }));
        } catch (reason) {
          axeError = reason instanceof Error ? reason.message : '无障碍审计未完成';
        }
        await atomicJson(path.join(evidence, 'audits', `${filename}.json`), {
          run_id: runId,
          state: item.id,
          mode: item.mode,
          route: item.url,
          theme,
          viewport,
          screenshot: `web/evidence/2026-10-19/07/screenshots/${filename}.png`,
          screenshot_sha256: hash(await fs.readFile(screenshot)),
          captured_at: new Date().toISOString(),
          ...visual,
          cinnabar_uses: accents,
          activity,
          violations,
          readiness_error: readinessError,
          axe_error: axeError,
        });
        expect.soft(readinessError).toBe('');
        expect.soft(axeError).toBe('');
        expect.soft(activity).toEqual({ api: [], external: [], errors: [], console: [] });
        expect.soft(visual.overflow).toBe(false);
        expect.soft(visual.font_faces).toBeGreaterThan(0);
        expect.soft(visual.rendered_theme).toBe(theme);
        expect.soft(visual.small_text).toEqual([]);
        expect.soft(accents.length, JSON.stringify(accents)).toBeLessThanOrEqual(3);
        expect.soft(violations).toEqual([]);
      });
    }
