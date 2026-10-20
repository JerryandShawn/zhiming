import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';

const runId = process.env.MINGJING_LIVE_VISUAL_RUN_ID ?? new Date().toISOString();
const batch = runId.replace(/[^a-zA-Z0-9-]/g, '-');
const evidence = path.resolve('test-results/live-evidence', batch);
const checkedIn = path.resolve(process.env.LIVE_VISUAL_SUMMARY_DIR || 'evidence/2026-10-18');
const names = ['today', 'chat', 'chart', 'tarot', 'cases', 'me', 'settings'] as const;
const viewports = [
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
];
let token = '',
  drawId = '',
  dayLabel = '';
type Audit = {
  run_id: string;
  name: string;
  theme: string;
  viewport: { width: number; height: number };
  screenshot: string;
  api_arrivals: string[];
  outside_requests: string[];
  page_errors: string[];
  model_trigger_requests: string[];
  overflow: boolean;
  font_faces: number;
  small_text: string[];
  violations: { id: string; impact: string | null | undefined; nodes: { target: unknown; summary?: string }[] }[];
};

test.beforeAll(async ({ request }) => {
  await fs.mkdir(path.join(evidence, 'screenshots'), { recursive: true });
  await fs.mkdir(path.join(evidence, 'audits'), { recursive: true });
  const created = await request.post('/__test__/owner');
  expect(created.ok()).toBe(true);
  token = ((await created.json()) as { token: string }).token;
  const headers = { 'X-Token': token };
  const snapshot = (await (await request.get('/api/state', { headers })).json()) as { revision: number };
  const confirmed = await request.post('/api/subjects/self/profile/confirm', {
    headers,
    data: {
      request_id: 'visual-profile',
      expected_revision: snapshot.revision,
      confirmed: true,
      profile: {
        gender: '女',
        birth: {
          solar_datetime: '1998-03-12 08:15',
          timezone_offset: 8,
          precision: 'exact',
          time_unknown: false,
          time_uncertainty_minutes: 0,
          location: { city: '合成地点', lng: 116.4, lat: 39.9 },
        },
      },
    },
  });
  expect(confirmed.ok()).toBe(true);
  const caseResponse = await request.post('/api/cases', {
    headers,
    data: { request_id: 'visual-case', title: '合成学习计划', goal: '先核对可用时间，再安排一个小步骤' },
  });
  expect(caseResponse.ok()).toBe(true);
  const caseId = ((await caseResponse.json()) as { id: string }).id;
  const drawResponse = await request.post('/api/tarot/draws', {
    headers,
    data: {
      idempotency_key: 'visual-fixed-draw',
      question: '如何安排这次合成学习计划？',
      case_id: caseId,
      subject_id: 'self',
      spread_id: 'reflect3',
      draw_source: 'auto',
      reversals: true,
    },
  });
  expect(drawResponse.ok()).toBe(true);
  drawId = ((await drawResponse.json()) as { draw: { id: string } }).draw.id;
  for (let position = 1; position <= 3; position++) {
    expect(
      (
        await request.post(`/api/tarot/draws/${drawId}/reveal`, {
          headers,
          data: { request_id: `visual-reveal-${position}`, position },
        })
      ).ok(),
    ).toBe(true);
  }
  const chart = await request.get('/api/chart?date=2026-10-18', { headers });
  expect(chart.ok()).toBe(true);
  dayLabel = ((await chart.json()) as { day: { day_ganzhi: string } }).day.day_ganzhi;
});

test.afterAll(async () => {
  await fs.mkdir(checkedIn, { recursive: true });
  const auditFiles = await fs.readdir(path.join(evidence, 'audits'));
  const audits = (
    await Promise.all(
      auditFiles
        .filter((name) => name.endsWith('.json'))
        .map(async (name) => JSON.parse(await fs.readFile(path.join(evidence, 'audits', name), 'utf8')) as Audit),
    )
  ).filter((audit) => audit.run_id === runId);
  const sources = await fs.readdir(path.resolve('src/live'));
  const sourceHashes = Object.fromEntries(
    await Promise.all(
      sources
        .filter((name) => /\.tsx?$/.test(name))
        .map(async (name) => [
          `web/src/live/${name}`,
          createHash('sha256')
            .update(await fs.readFile(path.resolve('src/live', name)))
            .digest('hex'),
        ]),
    ),
  );
  const assets = await fs.readdir(path.resolve('../static/dist/assets'));
  const buildHashes = Object.fromEntries(
    await Promise.all(
      assets
        .filter((name) => /\.(js|css)$/.test(name))
        .map(async (name) => [
          `static/dist/assets/${name}`,
          createHash('sha256')
            .update(await fs.readFile(path.resolve('../static/dist/assets', name)))
            .digest('hex'),
        ]),
    ),
  );
  const summary = {
    schema: 'frontend-v3-live-visual-v1',
    run_id: runId,
    captured_at: new Date().toISOString(),
    synthetic_only: true,
    backend: '127.0.0.1:8002 / core_test_fe',
    frontend: '127.0.0.1:4173',
    dedicated_owner: true,
    model_requests_sent_by_matrix: audits.reduce((sum, item) => sum + item.model_trigger_requests.length, 0),
    node_version: process.version,
    expected_combinations: 56,
    captured_combinations: audits.length,
    screenshots_directory: `web/test-results/live-evidence/${batch}/screenshots`,
    audits_directory: `web/test-results/live-evidence/${batch}/audits`,
    source_hashes: sourceHashes,
    build_hashes: buildHashes,
    checks: {
      overflowing: audits.filter((item) => item.overflow).length,
      external_requests: audits.reduce((sum, item) => sum + item.outside_requests.length, 0),
      javascript_errors: audits.reduce((sum, item) => sum + item.page_errors.length, 0),
      small_text_pages: audits.filter((item) => item.small_text.length).length,
      accessibility_violations: audits.reduce((sum, item) => sum + item.violations.length, 0),
    },
    findings: audits
      .filter(
        (item) =>
          item.overflow ||
          item.outside_requests.length ||
          item.page_errors.length ||
          item.violations.length ||
          item.small_text.length,
      )
      .map((item) => ({
        name: item.name,
        theme: item.theme,
        width: item.viewport.width,
        overflow: item.overflow,
        outside_requests: item.outside_requests,
        page_errors: item.page_errors,
        small_text: item.small_text,
        violations: item.violations,
      })),
    captures: audits.map((item) => ({
      name: item.name,
      theme: item.theme,
      width: item.viewport.width,
      screenshot: item.screenshot,
      api_arrivals: item.api_arrivals,
    })),
  };
  await fs.writeFile(path.join(checkedIn, 'live-visual-summary.json'), JSON.stringify(summary, null, 2) + '\n');
});

for (const viewport of viewports)
  for (const theme of ['light', 'dark'])
    for (const name of names) {
      test(`live ${name} ${theme} ${viewport.width}`, async ({ page }) => {
        await page.setViewportSize(viewport);
        await page.addInitScript(
          ({ token, theme }) => {
            sessionStorage.setItem('mingjing-auth-token', token);
            localStorage.setItem('mingjing-theme', theme);
          },
          { token, theme },
        );
        const outside: string[] = [],
          errors: string[] = [],
          calls: string[] = [],
          triggers: string[] = [];
        page.on('request', (request) => {
          const url = new URL(request.url());
          if (['http:', 'https:'].includes(url.protocol) && url.origin !== 'http://127.0.0.1:4173')
            outside.push(url.hostname);
          if (
            request.method() !== 'GET' &&
            (/^\/api\/chat$/.test(url.pathname) || /\/readings$|\/retry$|\/resume$/.test(url.pathname))
          )
            triggers.push(url.pathname);
        });
        page.on('response', (response) => {
          const url = new URL(response.url());
          if (url.pathname.startsWith('/api/') && response.ok()) calls.push(url.pathname);
        });
        page.on('pageerror', (error) => errors.push(error.name));
        const required: Record<(typeof names)[number], string[]> = {
          today: ['/api/chart', '/api/cases', '/api/history'],
          chat: ['/api/history'],
          chart: ['/api/chart'],
          tarot: ['/api/tarot/deck', `/api/tarot/draws/${drawId}`, `/api/tarot/draws/${drawId}/readings`],
          cases: ['/api/cases'],
          me: ['/api/memories', '/api/subjects/self/profile'],
          settings: ['/api/reports/schedules', '/api/state', '/api/health'],
        };
        const arrivals = required[name].map((endpoint) =>
          page.waitForResponse((response) => new URL(response.url()).pathname === endpoint && response.ok()),
        );
        const route =
          name === 'tarot' ? `tarot?draw=${drawId}` : name === 'chart' ? 'chart?tab=bazi&date=2026-10-18' : name;
        await page.goto(`/#/${route}`, { waitUntil: 'domcontentloaded' });
        await Promise.all(arrivals);
        await expect(page.locator(`[data-page="${name}"]`)).toBeVisible();
        if (name === 'today') await expect(page.getByRole('heading', { name: dayLabel })).toBeVisible();
        if (name === 'chart') await expect(page.getByRole('button', { name: /查看年柱.+依据/ })).toBeVisible();
        if (name === 'chat') await expect(page.getByText('这是飞书上的合成历史。', { exact: true })).toBeVisible();
        if (name === 'tarot') await expect(page.getByRole('button', { name: '全部揭开' })).toHaveCount(0);
        if (name === 'cases') await expect(page.getByRole('button', { name: /合成学习计划/ })).toBeVisible();
        if (name === 'me') await expect(page.getByRole('heading', { name: '核对出生资料' })).toBeVisible();
        if (name === 'settings') await expect(page.getByRole('button', { name: '保存晨报设置' })).toBeEnabled();
        await page.evaluate(() => document.fonts.ready);
        await page.waitForLoadState('networkidle');
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
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
                !element.closest('.citation, .calendar-mark, .calendar-festival'),
            )
            .map((element) => element.className),
        }));
        const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
        const filename = `${name}-${theme}-${viewport.width}`;
        const screenshot = `web/test-results/live-evidence/${batch}/screenshots/${filename}.png`;
        await page.screenshot({
          path: path.join(evidence, 'screenshots', `${filename}.png`),
          fullPage: true,
          animations: 'disabled',
        });
        const audit: Audit = {
          run_id: runId,
          name,
          theme,
          viewport,
          screenshot,
          api_arrivals: [...new Set(calls)].sort(),
          outside_requests: outside,
          page_errors: errors,
          model_trigger_requests: triggers,
          ...visual,
          violations: axe.violations.map((item) => ({
            id: item.id,
            impact: item.impact,
            nodes: item.nodes.map((node) => ({ target: node.target, summary: node.failureSummary })),
          })),
        };
        await fs.writeFile(path.join(evidence, 'audits', `${filename}.json`), JSON.stringify(audit, null, 2) + '\n');
        expect.soft(outside).toEqual([]);
        expect.soft(errors).toEqual([]);
        expect.soft(triggers).toEqual([]);
        expect.soft(visual.overflow).toBe(false);
        expect.soft(visual.small_text).toEqual([]);
        expect.soft(axe.violations).toEqual([]);
      });
    }
