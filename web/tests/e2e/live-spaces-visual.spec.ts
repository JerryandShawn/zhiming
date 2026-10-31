import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { cinnabarUsages } from './appearance';

const runId = process.env.MINGJING_LIVE_SPACES_VISUAL_RUN_ID ?? new Date().toISOString();
const batch = runId.replace(/[^a-zA-Z0-9-]/g, '-');
const evidence = path.resolve('evidence/2026-10-30/live-spaces');
const auditsDirectory = path.resolve('test-results/live-spaces-visual-evidence', batch, 'audits');
const viewports = [
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
];

type Audit = {
  run_id: string;
  theme: string;
  viewport: { width: number; height: number };
  screenshot: string;
  screenshot_sha256: string;
  api_requests: string[];
  outside_requests: string[];
  page_errors: string[];
  console_messages: { type: string; text: string }[];
  overflow: boolean;
  small_text: string[];
  cinnabar_uses: { className: string; text?: string }[];
  violations: { id: string; impact: string | null | undefined; nodes: { target: unknown; summary?: string }[] }[];
};

async function hashFile(filename: string) {
  return createHash('sha256')
    .update(await fs.readFile(filename))
    .digest('hex');
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
  const summary = {
    schema: 'frontend-live-spaces-visual-v1',
    run_id: runId,
    captured_at: new Date().toISOString(),
    node_version: process.version,
    frontend: 'http://127.0.0.1:4173',
    mode: '?spaces=demo#/spaces?space=career; synthetic in-memory service; no API or storage',
    expected_combinations: 8,
    captured_combinations: audits.length,
    source_hashes: Object.fromEntries(
      await Promise.all(
        [
          'src/App.tsx',
          'src/spaces/LiveSpaces.tsx',
          'src/spaces/fakeServer.ts',
          'src/spaces/http.ts',
          'src/spaces/live-spaces.css',
          'tests/e2e/live-spaces.spec.ts',
          'tests/e2e/live-spaces-visual.spec.ts',
          'playwright.live-spaces-visual.config.ts',
        ].map(async (file) => [`web/${file}`, await hashFile(path.resolve(file))]),
      ),
    ),
    checks: {
      api_requests: audits.reduce((sum, item) => sum + item.api_requests.length, 0),
      external_requests: audits.reduce((sum, item) => sum + item.outside_requests.length, 0),
      javascript_errors: audits.reduce((sum, item) => sum + item.page_errors.length, 0),
      console_messages: audits.reduce((sum, item) => sum + item.console_messages.length, 0),
      overflowing_pages: audits.filter((item) => item.overflow).length,
      small_text_pages: audits.filter((item) => item.small_text.length).length,
      cinnabar_budget_failures: audits.filter((item) => item.cinnabar_uses.length > 3).length,
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
        item.cinnabar_uses.length > 3 ||
        item.violations.length,
    ),
    captures: audits.map((item) => ({
      theme: item.theme,
      viewport: item.viewport,
      screenshot: item.screenshot,
      sha256: item.screenshot_sha256,
    })),
  };
  await fs.writeFile(path.join(evidence, 'visual-summary.json'), JSON.stringify(summary, null, 2) + '\n');
});

for (const viewport of viewports)
  for (const theme of ['light', 'dark'])
    test(`live spaces ${theme} ${viewport.width}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
      const api: string[] = [],
        outside: string[] = [],
        errors: string[] = [];
      const consoleMessages: Audit['console_messages'] = [];
      page.on('request', (request) => {
        const url = new URL(request.url());
        if (url.pathname.startsWith('/api/')) api.push(`${request.method()} ${url.pathname}`);
        if (['http:', 'https:'].includes(url.protocol) && url.origin !== 'http://127.0.0.1:4173')
          outside.push(url.origin);
      });
      page.on('pageerror', (error) => errors.push(`${error.name}: ${error.message}`));
      page.on('console', (message) => {
        if (['warning', 'error'].includes(message.type()))
          consoleMessages.push({ type: message.type(), text: message.text() });
      });
      await page.goto('/?spaces=demo#/spaces?space=career', { waitUntil: 'domcontentloaded' });
      await expect(page.locator('[data-page="spaces"][data-runtime="spaces-fake"]')).toBeVisible();
      await expect(page.getByRole('heading', { name: '事业的话题', exact: true })).toBeVisible();
      await expect(page.getByRole('heading', { name: '合成样例：是否换岗', exact: true })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await page.waitForLoadState('networkidle');
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      const visual = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth > innerWidth,
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
      const cinnabar = await page.evaluate(cinnabarUsages);
      const axe = await new AxeBuilder({ page }).analyze();
      const filename = `spaces-${theme}-${viewport.width}`;
      const screenshotFile = path.join(evidence, 'screenshots', `${filename}.png`);
      await page.screenshot({ path: screenshotFile, fullPage: true, animations: 'disabled' });
      const audit: Audit = {
        run_id: runId,
        theme,
        viewport,
        screenshot: `web/evidence/2026-10-30/live-spaces/screenshots/${filename}.png`,
        screenshot_sha256: await hashFile(screenshotFile),
        api_requests: api,
        outside_requests: outside,
        page_errors: errors,
        console_messages: consoleMessages,
        ...visual,
        cinnabar_uses: cinnabar,
        violations: axe.violations.map((violation) => ({
          id: violation.id,
          impact: violation.impact,
          nodes: violation.nodes.map((node) => ({ target: node.target, summary: node.failureSummary })),
        })),
      };
      await fs.writeFile(path.join(auditsDirectory, `${filename}.json`), JSON.stringify(audit, null, 2) + '\n');
      expect.soft(api).toEqual([]);
      expect.soft(outside).toEqual([]);
      expect.soft(errors).toEqual([]);
      expect.soft(consoleMessages).toEqual([]);
      expect.soft(visual.overflow).toBe(false);
      expect.soft(visual.small_text).toEqual([]);
      expect.soft(cinnabar.length).toBeLessThanOrEqual(3);
      expect.soft(axe.violations).toEqual([]);
    });
