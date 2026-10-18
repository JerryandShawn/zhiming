import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';

const runId = process.env.MINGJING_SPACES_VISUAL_RUN_ID ?? new Date().toISOString();
const batch = runId.replace(/[^a-zA-Z0-9-]/g, '-');
const evidence = path.resolve('evidence/2026-10-18/spaces');
const auditsDirectory = path.resolve('test-results/spaces-visual-evidence', batch, 'audits');
const pages = [
  { name: 'chat', route: 'chat?space=career&topic=interview', heading: '跳槽 · 面试' },
  { name: 'me', route: 'me', heading: '关于我 · 分区记忆' },
  { name: 'organize', route: 'organize', heading: '整理建议' },
] as const;
const viewports = [
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
];

interface Audit {
  run_id: string;
  name: string;
  route: string;
  theme: string;
  viewport: { width: number; height: number };
  screenshot: string;
  screenshot_sha256: string;
  api_requests: string[];
  outside_requests: string[];
  page_errors: string[];
  console_messages: { type: string; text: string }[];
  overflow: boolean;
  font_faces: number;
  small_text: string[];
  violations: { id: string; impact: string | null | undefined; nodes: { target: unknown; summary?: string }[] }[];
}

async function hashFile(filename: string) {
  return createHash('sha256')
    .update(await fs.readFile(filename))
    .digest('hex');
}

async function fileHashes(directory: string, prefix: string, extensions: RegExp) {
  const entries = await fs.readdir(directory, { withFileTypes: true });
  const result: Record<string, string> = {};
  for (const entry of entries) {
    const filename = path.join(directory, entry.name);
    if (entry.isFile() && extensions.test(entry.name)) result[`${prefix}/${entry.name}`] = await hashFile(filename);
  }
  return result;
}

test.beforeAll(async () => {
  await fs.mkdir(path.join(evidence, 'screenshots'), { recursive: true });
  await fs.mkdir(auditsDirectory, { recursive: true });
});

test.afterAll(async () => {
  const files = await fs.readdir(auditsDirectory);
  const audits = (
    await Promise.all(
      files
        .filter((file) => file.endsWith('.json'))
        .map(async (file) => JSON.parse(await fs.readFile(path.join(auditsDirectory, file), 'utf8')) as Audit),
    )
  ).filter((item) => item.run_id === runId);
  const sourceHashes = await fileHashes(path.resolve('src/spaces'), 'web/src/spaces', /\.(tsx?|css)$/);
  for (const filename of [
    'src/App.tsx',
    'src/Layout.tsx',
    'src/styles/base.css',
    'index.html',
    'tests/e2e/spaces.spec.ts',
    'tests/e2e/spaces-visual.spec.ts',
    'playwright.spaces-visual.config.ts',
  ])
    sourceHashes[`web/${filename}`] = await hashFile(path.resolve(filename));
  const buildHashes = await fileHashes(path.resolve('../static/dist/assets'), 'static/dist/assets', /\.(js|css)$/);
  buildHashes['static/dist/index.html'] = await hashFile(path.resolve('../static/dist/index.html'));
  buildHashes['static/dist/.vite/manifest.json'] = await hashFile(path.resolve('../static/dist/.vite/manifest.json'));
  const summary = {
    schema: 'frontend-spaces-demo-visual-v1',
    run_id: runId,
    captured_at: new Date().toISOString(),
    node_version: process.version,
    frontend: 'http://127.0.0.1:4173',
    mode: '?spaces=demo; synthetic in-memory fixtures; refresh resets',
    synthetic_only: true,
    backend_required: false,
    model_requests: 0,
    expected_combinations: 24,
    captured_combinations: audits.length,
    screenshots_directory: 'web/evidence/2026-10-18/spaces/screenshots',
    raw_audits_directory: `web/test-results/spaces-visual-evidence/${batch}/audits`,
    source_hashes: sourceHashes,
    build_hashes: buildHashes,
    checks: {
      api_requests: audits.reduce((sum, item) => sum + item.api_requests.length, 0),
      external_requests: audits.reduce((sum, item) => sum + item.outside_requests.length, 0),
      javascript_errors: audits.reduce((sum, item) => sum + item.page_errors.length, 0),
      console_messages: audits.reduce((sum, item) => sum + item.console_messages.length, 0),
      overflowing_pages: audits.filter((item) => item.overflow).length,
      small_text_pages: audits.filter((item) => item.small_text.length).length,
      accessibility_violations: audits.reduce((sum, item) => sum + item.violations.length, 0),
    },
    findings: audits.filter(
      (item) =>
        item.api_requests.length ||
        item.outside_requests.length ||
        item.page_errors.length ||
        item.console_messages.length ||
        item.overflow ||
        item.small_text.length ||
        item.violations.length,
    ),
    captures: audits.map((item) => ({
      name: item.name,
      route: item.route,
      theme: item.theme,
      viewport: item.viewport,
      screenshot: item.screenshot,
      sha256: item.screenshot_sha256,
      font_faces: item.font_faces,
    })),
  };
  await fs.writeFile(path.join(evidence, 'visual-summary.json'), JSON.stringify(summary, null, 2) + '\n');
});

for (const viewport of viewports)
  for (const theme of ['light', 'dark'])
    for (const item of pages) {
      test(`spaces ${item.name} ${theme} ${viewport.width}`, async ({ page }) => {
        await page.setViewportSize(viewport);
        await page.addInitScript((theme) => {
          localStorage.setItem('mingjing-theme', theme);
        }, theme);
        const api: string[] = [],
          outside: string[] = [],
          errors: string[] = [];
        const consoleMessages: Audit['console_messages'] = [];
        page.on('request', (request) => {
          const url = new URL(request.url());
          if (/^\/api(?:\/|$)/.test(url.pathname)) api.push(`${request.method()} ${url.pathname}`);
          if (['http:', 'https:'].includes(url.protocol) && url.origin !== 'http://127.0.0.1:4173')
            outside.push(url.origin);
        });
        page.on('pageerror', (error) => errors.push(`${error.name}: ${error.message}`));
        page.on('console', (message) => consoleMessages.push({ type: message.type(), text: message.text() }));
        const route = `/?spaces=demo#/${item.route}`;
        await page.goto(route, { waitUntil: 'domcontentloaded' });
        await expect(page.locator(`[data-page="${item.name}"]`)).toBeVisible();
        await expect(page.getByRole('heading', { name: item.heading, exact: true })).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
        await page.waitForLoadState('networkidle');
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
        if (item.name === 'chat') {
          await expect(page.locator('[data-message]')).toHaveCount(4);
          if (viewport.width >= 1024) await expect(page.getByRole('complementary', { name: '话题列表' })).toBeVisible();
          else await expect(page.getByRole('combobox', { name: '当前话题' })).toBeVisible();
        }
        const visual = await page.evaluate(() => ({
          overflow: document.documentElement.scrollWidth > innerWidth,
          font_faces: document.fonts.size,
          small_text: Array.from(document.querySelectorAll('main *'))
            .filter(
              (element) =>
                element instanceof HTMLElement &&
                Array.from(element.childNodes).some((node) => node.nodeType === 3 && node.textContent?.trim()) &&
                element.getBoundingClientRect().width > 0 &&
                getComputedStyle(element).display !== 'none' &&
                parseFloat(getComputedStyle(element).fontSize) < 13 &&
                !element.closest('.citation'),
            )
            .map((element) => element.className),
        }));
        const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
        const filename = `${item.name}-${theme}-${viewport.width}.png`;
        const screenshotFile = path.join(evidence, 'screenshots', filename);
        await page.screenshot({ path: screenshotFile, fullPage: true, animations: 'disabled' });
        const audit: Audit = {
          run_id: runId,
          name: item.name,
          route,
          theme,
          viewport,
          screenshot: `web/evidence/2026-10-18/spaces/screenshots/${filename}`,
          screenshot_sha256: await hashFile(screenshotFile),
          api_requests: api,
          outside_requests: outside,
          page_errors: errors,
          console_messages: consoleMessages,
          ...visual,
          violations: axe.violations.map((violation) => ({
            id: violation.id,
            impact: violation.impact,
            nodes: violation.nodes.map((node) => ({ target: node.target, summary: node.failureSummary })),
          })),
        };
        await fs.writeFile(
          path.join(auditsDirectory, filename.replace('.png', '.json')),
          JSON.stringify(audit, null, 2) + '\n',
        );
        expect.soft(api).toEqual([]);
        expect.soft(outside).toEqual([]);
        expect.soft(errors).toEqual([]);
        expect.soft(consoleMessages).toEqual([]);
        expect.soft(visual.overflow).toBe(false);
        expect.soft(visual.small_text).toEqual([]);
        expect.soft(axe.violations).toEqual([]);
      });
    }
