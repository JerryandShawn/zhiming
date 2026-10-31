import { expect, type BrowserContext, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { cinnabarUsages } from './appearance';

export const q9Origin = 'http://127.0.0.1:4173';
const web = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
export const capturedBjt = () => new Date(Date.now() + 28800000).toISOString().replace('Z', '+08:00');
const hash = (bytes: Uint8Array | string) => createHash('sha256').update(bytes).digest('hex');
export function q9Directory() {
  const id = process.env.MINGJING_Q9_RUN_ID ?? '';
  if (!/^[A-Za-z0-9-]{1,140}$/.test(id)) throw new Error('A unique safe MINGJING_Q9_RUN_ID is required');
  return path.join(web, 'evidence/2026-10-21/Q9/night', id);
}
async function json(filename: string, value: unknown) {
  await fs.writeFile(filename, JSON.stringify(value, null, 2) + '\n', { flag: 'wx' });
}
async function fingerprints() {
  const files: Record<string, string> = {};
  async function walk(directory: string) {
    for (const entry of (await fs.readdir(directory, { withFileTypes: true })).sort((a, b) =>
      a.name.localeCompare(b.name),
    )) {
      const name = path.join(directory, entry.name);
      if (entry.isDirectory()) await walk(name);
      else if (entry.isFile()) files[path.relative(web, name).replaceAll('\\', '/')] = hash(await fs.readFile(name));
    }
  }
  for (const name of ['src', 'public', '../static/dist']) await walk(path.resolve(web, name));
  for (const name of [
    'index.html',
    'vite.config.ts',
    'pwa.plugin.ts',
    'playwright.q9-night.config.ts',
    'tests/e2e/q9-night-helpers.ts',
    'tests/e2e/q9-night-visual.spec.ts',
  ])
    files[name] = hash(await fs.readFile(path.join(web, name)));
  const git = (args: string[]) =>
    execFileSync('git', args, { cwd: web, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 }).trim();
  return {
    base_HEAD: git(['rev-parse', 'HEAD']),
    dirty_diff_sha256: hash(
      git([
        'diff',
        '--binary',
        'HEAD',
        '--',
        'src',
        'public',
        'index.html',
        'vite.config.ts',
        'pwa.plugin.ts',
        'tests/e2e/q9-night-helpers.ts',
        'tests/e2e/q9-night-visual.spec.ts',
        'playwright.q9-night.config.ts',
      ]),
    ),
    files,
  };
}

/** Exclusive directory creation refuses a reused run id, including a previously partial run. */
export default async function setupQ9() {
  const directory = q9Directory();
  await fs.mkdir(path.dirname(directory), { recursive: true });
  await fs.mkdir(directory);
  await fs.mkdir(path.join(directory, 'screenshots'));
  await fs.mkdir(path.join(directory, 'audits'));
  const before = await fingerprints();
  await json(path.join(directory, 'run.json'), {
    run_id: process.env.MINGJING_Q9_RUN_ID,
    captured_time_bjt: capturedBjt(),
    expected_combinations: 112,
    synthetic_only: true,
    backend_required: false,
    ...before,
  });
  return async () => {
    const after = await fingerprints();
    const stable = JSON.stringify(before) === JSON.stringify(after);
    await json(path.join(directory, 'closing.json'), {
      captured_time_bjt: capturedBjt(),
      immutable_source_and_build: stable,
      ...after,
    });
    if (!stable) throw new Error('Q9 source/build changed during capture; this run cannot be accepted');
  };
}

export type Q9Activity = { api: string[]; external: string[]; errors: string[]; console: string[]; failed: string[] };
export async function guardQ9(context: BrowserContext, page: Page): Promise<Q9Activity> {
  const activity: Q9Activity = { api: [], external: [], errors: [], console: [], failed: [] };
  const forbidden = (url: URL) => /^\/(?:api|static|__test__|__frontend_fixture__)(?:\/|$)/.test(url.pathname);
  context.on('request', (request) => {
    const url = new URL(request.url());
    if (url.origin === q9Origin && forbidden(url)) activity.api.push(`${request.method()} ${url.pathname}`);
    if (['http:', 'https:'].includes(url.protocol) && url.origin !== q9Origin) activity.external.push(url.origin);
  });
  await context.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (['http:', 'https:'].includes(url.protocol) && (url.origin !== q9Origin || forbidden(url))) await route.abort();
    else await route.continue();
  });
  page.on('pageerror', (error) => activity.errors.push(error.message));
  page.on('console', (message) => activity.console.push(`${message.type()}: ${message.text()}`));
  page.on('requestfailed', (request) =>
    activity.failed.push(`${new URL(request.url()).pathname}: ${request.failure()?.errorText}`),
  );
  return activity;
}

export type Q9Screen = {
  kind: string;
  selector: string;
  index: number;
  document_y: number;
  scroll_top: number;
  cinnabar_uses: ReturnType<typeof cinnabarUsages>;
  small_text: { className: string; tag: string; font_size: number }[];
};
export type Q9Inspection = {
  document: { lang: string; theme: string | undefined; font_faces: number; overflow: boolean };
  screens: Q9Screen[];
  violations: {
    id: string;
    impact: string | null | undefined;
    nodes: { target: unknown; summary: string | undefined }[];
  }[];
};
const settle = (page: Page) =>
  page.evaluate(
    () => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))),
  );

/** Reusable visual audit: no route, evidence directory or network assumptions. */
export async function inspectQ9(page: Page): Promise<Q9Inspection> {
  const screens: Q9Screen[] = [];
  async function sample(kind: string, selector = '', index = 0) {
    await settle(page);
    const values = await page.evaluate(
      ({ selector, index }) => {
        const visible = (element: Element) => {
          const rect = element.getBoundingClientRect();
          let top = Math.max(0, rect.top),
            bottom = Math.min(innerHeight, rect.bottom),
            left = Math.max(0, rect.left),
            right = Math.min(innerWidth, rect.right);
          for (let parent: Element | null = element; parent; parent = parent.parentElement) {
            const css = getComputedStyle(parent),
              bounds = parent.getBoundingClientRect();
            if (css.display === 'none' || css.visibility === 'hidden' || Number(css.opacity) === 0) return false;
            if (/(auto|scroll|hidden|clip)/.test(css.overflowY)) {
              top = Math.max(top, bounds.top);
              bottom = Math.min(bottom, bounds.bottom);
            }
            if (/(auto|scroll|hidden|clip)/.test(css.overflowX)) {
              left = Math.max(left, bounds.left);
              right = Math.min(right, bounds.right);
            }
          }
          return bottom > top && right > left;
        };
        const portals = [
          ...document.querySelectorAll('[role="dialog"], [role="alertdialog"], [data-radix-popper-content-wrapper]'),
        ].filter(visible);
        const modal = portals.find((node) => node.getAttribute('aria-modal') === 'true');
        const roots = modal ? [modal] : [...document.querySelectorAll('main'), ...portals];
        const nodes = new Set(roots.flatMap((root) => [root, ...root.querySelectorAll('*')]));
        const small_text = [...nodes]
          .filter(
            (element) =>
              visible(element) &&
              [...element.childNodes].some((node) => node.nodeType === 3 && node.textContent?.trim()) &&
              parseFloat(getComputedStyle(element).fontSize) < 13 &&
              // Seal's hidden SVG is the labelled brand artwork, not reading text.
              !element.closest('.seal[role="img"] svg[aria-hidden="true"]') &&
              !element.closest('.citation, .calendar-mark, .calendar-festival'),
          )
          .map((element) => ({
            className: element.getAttribute('class') ?? '',
            tag: element.tagName,
            font_size: parseFloat(getComputedStyle(element).fontSize),
          }));
        return {
          document_y: scrollY,
          scroll_top: selector ? (document.querySelectorAll(selector)[index]?.scrollTop ?? 0) : 0,
          small_text,
        };
      },
      { selector, index },
    );
    screens.push({ kind, selector, index, ...values, cinnabar_uses: await page.evaluate(cinnabarUsages) });
  }
  const scrollers = '.chat-messages, [role="dialog"], [role="alertdialog"]';
  await page.evaluate((selector) => {
    scrollTo(0, 0);
    document.querySelectorAll(selector).forEach((node) => {
      node.scrollTop = 0;
    });
  }, scrollers);
  const geometry = await page.evaluate(() => ({
    maximum: Math.max(0, (document.scrollingElement?.scrollHeight ?? innerHeight) - innerHeight),
    step: Math.max(1, innerHeight - 120),
  }));
  const positions = new Set([0, geometry.maximum]);
  for (let y = geometry.step; y < geometry.maximum; y += geometry.step) positions.add(y);
  for (const y of [...positions].sort((a, b) => a - b)) {
    await page.evaluate((y) => scrollTo(0, y), y);
    await sample('document');
  }
  const count = await page.locator(scrollers).count();
  for (let index = 0; index < count; index++) {
    const geometry = await page
      .locator(scrollers)
      .nth(index)
      .evaluate((element) => ({
        maximum: Math.max(0, element.scrollHeight - element.clientHeight),
        step: Math.max(1, element.clientHeight - 80),
        visible: element.getBoundingClientRect().height > 0,
      }));
    if (!geometry.maximum || !geometry.visible) continue;
    await page.locator(scrollers).nth(index).scrollIntoViewIfNeeded();
    const positions = new Set([0, geometry.maximum]);
    for (let top = geometry.step; top < geometry.maximum; top += geometry.step) positions.add(top);
    for (const top of [...positions].sort((a, b) => a - b)) {
      await page
        .locator(scrollers)
        .nth(index)
        .evaluate((element, top) => {
          element.scrollTop = top;
        }, top);
      await sample('internal', scrollers, index);
    }
  }
  await page.evaluate((selector) => {
    scrollTo(0, 0);
    document.querySelectorAll(selector).forEach((node) => {
      node.scrollTop = 0;
    });
  }, scrollers);
  await settle(page);
  const documentInfo = await page.evaluate(() => ({
    lang: document.documentElement.lang,
    theme: document.documentElement.dataset.theme,
    font_faces: document.fonts.size,
    overflow: document.documentElement.scrollWidth > innerWidth,
  }));
  const violations = (await new AxeBuilder({ page }).analyze()).violations.map((item) => ({
    id: item.id,
    impact: item.impact,
    nodes: item.nodes.map((node) => ({ target: node.target, summary: node.failureSummary })),
  }));
  return { document: documentInfo, screens, violations };
}

export function assertQ9Inspection(audit: Q9Inspection, theme: string) {
  expect.soft(audit.document.lang).toBe('zh-CN');
  expect.soft(audit.document.theme).toBe(theme);
  expect.soft(audit.document.font_faces).toBeGreaterThan(0);
  expect.soft(audit.document.overflow).toBe(false);
  expect.soft(audit.screens.length).toBeGreaterThan(0);
  for (const screen of audit.screens) {
    expect.soft(screen.small_text, JSON.stringify(screen)).toEqual([]);
    expect.soft(screen.cinnabar_uses.length, JSON.stringify(screen)).toBeLessThanOrEqual(3);
  }
  expect.soft(audit.violations).toEqual([]);
}

export async function captureQ9(
  page: Page,
  key: string,
  metadata: Record<string, unknown>,
  activity: Q9Activity,
  readinessError = '',
) {
  const inspection = await inspectQ9(page),
    directory = q9Directory();
  const images = [];
  for (const fullPage of [false, true]) {
    const filename = `${key}${fullPage ? '-full' : ''}.png`,
      bytes = await page.screenshot({ fullPage, animations: 'disabled' });
    await fs.writeFile(path.join(directory, 'screenshots', filename), bytes, { flag: 'wx' });
    images.push({
      screenshot: `web/${path.relative(web, path.join(directory, 'screenshots', filename)).replaceAll('\\', '/')}`,
      sha256: hash(bytes),
      full_page: fullPage,
    });
  }
  await json(path.join(directory, 'audits', `${key}.json`), {
    run_id: process.env.MINGJING_Q9_RUN_ID,
    captured_time_bjt: capturedBjt(),
    id: metadata.state,
    case_key: key,
    ...metadata,
    screenshot: images[0].screenshot,
    screenshot_sha256: images[0].sha256,
    full_screenshot: images[1].screenshot,
    images,
    ...inspection,
    activity,
    readiness_error: readinessError,
    manual_review_required: [
      'one-main-task',
      'token-color-use',
      'no-decorative-English-or-symbol-icons',
      'spacing-and-interaction-only-cards',
      'dark-chart-legibility',
      'reference-side-by-side-differences',
    ],
    counting: '14 I.6; each document/internal-scroll viewport; brand/navigation/chart semantic colors excluded',
  });
  expect.soft(readinessError).toBe('');
  expect.soft(activity).toEqual({ api: [], external: [], errors: [], console: [], failed: [] });
  assertQ9Inspection(inspection, String(metadata.theme));
}
