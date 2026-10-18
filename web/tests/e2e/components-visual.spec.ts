import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { assertDemoQuiet, componentEvidence, demoActivity, guardDemo, openDemo } from './components-helpers';

const runId = process.env.MINGJING_COMPONENTS_RUN_ID!;
const stage = process.env.MINGJING_COMPONENTS_STAGE ?? 'chart';
const batch = runId.replace(/[^a-zA-Z0-9-]/g, '-');
const auditsDirectory = `test-results/components-evidence/${batch}/audits`;
const states = [
  { stage: 'chart', name: 'bazi', route: 'chart?tab=bazi' },
  { stage: 'chart', name: 'ziwei', route: 'chart?tab=ziwei' },
  { stage: 'chart', name: 'astro', route: 'chart?tab=astro' },
  { stage: 'tarot', name: 'tarot-focus1', route: 'tarot?spread=focus1&step=reveal' },
  { stage: 'tarot', name: 'tarot-reflect3', route: 'tarot?spread=reflect3&step=reveal' },
  { stage: 'tarot', name: 'tarot-choice5', route: 'tarot?spread=choice5&step=reveal' },
  { stage: 'tarot', name: 'tarot-picker', route: 'tarot?spread=reflect3&step=pick' },
  { stage: 'calendar', name: 'today', route: 'today' },
] as const;
const viewports = [
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
];
const selectedStates = states.filter((state) => stage === 'all' || state.stage === stage);
const hash = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');

async function sourceHashes(directory: string): Promise<Record<string, string>> {
  const results: Record<string, string> = {};
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory()) Object.assign(results, await sourceHashes(filename));
    else if (/\.(tsx?|css|html|js)$/.test(entry.name))
      results[`web/${filename.replaceAll('\\', '/')}`] = hash(await fs.readFile(filename));
  }
  return results;
}
async function prepareState(page: Page, item: (typeof states)[number]) {
  await openDemo(page, item.route);
  if (item.stage === 'tarot' && item.name !== 'tarot-picker') {
    await page.getByRole('button', { name: '全部揭开', exact: true }).click();
    await expect(page.locator('.tarot-flip-front')).toHaveCount(
      { 'tarot-focus1': 1, 'tarot-reflect3': 3, 'tarot-choice5': 5 }[item.name]!,
    );
  }
  if (item.stage === 'chart')
    await expect(page.getByRole('group', { name: '命盘体系' }).getByRole('button', { pressed: true })).toHaveText(
      { bazi: '八字', ziwei: '紫微', astro: '星盘' }[item.name]!,
    );
}

test.beforeAll(async () => {
  await fs.mkdir(`${componentEvidence}/screenshots`, { recursive: true });
  await fs.mkdir(auditsDirectory, { recursive: true });
});
test.afterAll(async () => {
  const audits = await Promise.all(
    (await fs.readdir(auditsDirectory)).map(
      async (name) => JSON.parse(await fs.readFile(`${auditsDirectory}/${name}`, 'utf8')) as Record<string, unknown>,
    ),
  );
  const build: Record<string, string> = {};
  for (const name of await fs.readdir('../static/dist/assets'))
    if (/\.(css|js)$/.test(name))
      build[`static/dist/assets/${name}`] = hash(await fs.readFile(`../static/dist/assets/${name}`));
  for (const name of ['index.html', '.vite/manifest.json'])
    build[`static/dist/${name}`] = hash(await fs.readFile(`../static/dist/${name}`));
  const sources = await sourceHashes('src');
  sources['web/tests/e2e/components-visual.spec.ts'] = hash(await fs.readFile('tests/e2e/components-visual.spec.ts'));
  const summary = {
    run_id: runId,
    stage,
    captured_at: new Date().toISOString(),
    node: process.version,
    synthetic_only: true,
    model_calls: 0,
    expected_combinations: selectedStates.length * viewports.length * 2,
    captured_combinations: audits.length,
    source_hashes: sources,
    build_hashes: build,
    captures: audits,
  };
  await fs.writeFile(`${componentEvidence}/${stage}-visual-summary.json`, JSON.stringify(summary, null, 2) + '\n');
});

for (const viewport of viewports)
  for (const theme of ['light', 'dark'])
    for (const item of selectedStates)
      test(`${item.stage} ${item.name} ${theme} ${viewport.width}`, async ({ page }) => {
        await page.setViewportSize(viewport);
        await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
        guardDemo(page);
        await prepareState(page, item);
        await page.waitForLoadState('networkidle');
        const visual = await page.evaluate(() => ({
          overflow: document.documentElement.scrollWidth > innerWidth,
          small_text: Array.from(document.querySelectorAll('main *'))
            .filter((element) => {
              if (!(element instanceof HTMLElement)) return false;
              const rect = element.getBoundingClientRect(),
                style = getComputedStyle(element);
              return (
                rect.width > 0 &&
                rect.height > 0 &&
                style.display !== 'none' &&
                Array.from(element.childNodes).some((node) => node.nodeType === 3 && node.textContent?.trim()) &&
                parseFloat(style.fontSize) < 13 &&
                !element.closest('.citation, .calendar-mark, .calendar-festival')
              );
            })
            .map((element) => element.className),
        }));
        const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
        await page.evaluate(() => window.scrollTo(0, 0));
        const filename = `${item.name}-${theme}-${viewport.width}.png`;
        const screenshot = `${componentEvidence}/screenshots/${filename}`;
        await page.screenshot({ path: screenshot, fullPage: true, animations: 'disabled' });
        const audit = {
          run_id: runId,
          state: item.name,
          route: item.route,
          theme,
          viewport,
          screenshot: `web/${screenshot}`,
          screenshot_sha256: hash(await fs.readFile(screenshot)),
          ...visual,
          activity: demoActivity(page),
          violations: axe.violations.map((violation) => ({
            id: violation.id,
            impact: violation.impact,
            nodes: violation.nodes.map((node) => ({ target: node.target, summary: node.failureSummary })),
          })),
        };
        await fs.writeFile(`${auditsDirectory}/${filename}.json`, JSON.stringify(audit, null, 2) + '\n');
        assertDemoQuiet(page);
        expect(visual.overflow).toBe(false);
        expect(visual.small_text).toEqual([]);
        expect(axe.violations).toEqual([]);
      });
