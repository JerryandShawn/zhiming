import { expect, type APIRequestContext, type Page } from '@playwright/test';
import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { inspectQ9, assertQ9Inspection } from './q9-night-helpers';

export const frontend = 'http://127.0.0.1:4173';
export const backend = 'http://127.0.0.1:8002';
export const fixedTime = '2026-10-21T10:00:00+08:00';
export const fixedDate = '2026-10-21';
export const names = ['today', 'chat', 'chart', 'tarot', 'cases', 'me', 'settings'] as const;
export type Name = (typeof names)[number];
export type Seed = { token: string; drawId: string; dayLabel: string; caseTitle: string; question: string };
export type Activity = {
  arrivals: { path: string; status: number }[];
  external: string[];
  writes: string[];
  errors: string[];
  console: string[];
  failed: string[];
  expected_cancellations: string[];
  http_errors: { path: string; status: number }[];
};
const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const batch = (process.env.Q9_V3_RUN_ID ?? 'missing-run-id').replace(/[^a-zA-Z0-9-]/g, '-');
export const evidence = path.resolve(webRoot, 'evidence/2026-10-21/Q9/v3', batch);
const digest = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');
const repositoryPath = (file: string) => `web/${path.relative(webRoot, file).split(path.sep).join('/')}`;
const beijingNow = () =>
  new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  })
    .format(new Date())
    .replace(' ', 'T') + '+08:00';

export async function writeEvidence(file: string, value: unknown) {
  if (batch === 'missing-run-id' || path.basename(file) !== file)
    throw new Error('A safe unique Q9 evidence run is required');
  await fs.mkdir(evidence, { recursive: true });
  await fs.writeFile(path.join(evidence, file), JSON.stringify(value, null, 2) + '\n', { flag: 'wx' });
}

export async function fixtureSafety(api: APIRequestContext) {
  const response = await api.get('/__test__/metrics');
  expect(response.ok(), 'The isolated fixture metrics endpoint must respond').toBe(true);
  const metrics = (await response.json()) as {
    database: string;
    model: string;
    real_model_calls: number;
    provider_calls: number;
  };
  expect(metrics.database).toBe('core_test_fe');
  expect(metrics.model).toBe('scripted-only');
  expect(metrics.real_model_calls).toBe(0);
  return metrics;
}

export async function guardV3(page: Page, name: Name): Promise<Activity> {
  const activity: Activity = {
    arrivals: [],
    external: [],
    writes: [],
    errors: [],
    console: [],
    failed: [],
    expected_cancellations: [],
    http_errors: [],
  };
  page.on('pageerror', (error) => activity.errors.push(error.name));
  page.on('console', (message) => {
    const location = message.location();
    const pathname = location.url ? new URL(location.url, frontend).pathname : 'unknown';
    activity.console.push(`${message.type()}:${pathname}:${location.lineNumber ?? 0}`);
  });
  page.on('requestfailed', (request) => {
    const pathname = new URL(request.url()).pathname;
    const error = request.failure()?.errorText ?? 'unknown';
    const detail = `${request.method()} ${pathname}: ${error}`;
    // Restoring a fixed draw unmounts QuestionForm and cancels its React Query GET.
    // Only this exact cancellation is expected; all other failures stay fatal.
    if (name === 'tarot' && request.method() === 'GET' && pathname === '/api/cases' && error === 'net::ERR_ABORTED')
      activity.expected_cancellations.push(detail);
    else activity.failed.push(detail);
  });
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (!url.pathname.startsWith('/api/')) return;
    const result = { path: url.pathname, status: response.status() };
    if (response.ok()) activity.arrivals.push(result);
    else activity.http_errors.push(result);
  });
  await page.route('**/*', async (route) => {
    const request = route.request(),
      url = new URL(request.url());
    if (['http:', 'https:'].includes(url.protocol) && url.origin !== frontend) {
      activity.external.push(url.origin);
      return route.abort();
    }
    if (url.pathname.startsWith('/__test__/') || (url.pathname.startsWith('/api/') && request.method() !== 'GET')) {
      activity.writes.push(`${request.method()} ${url.pathname}`);
      return route.abort();
    }
    return route.continue();
  });
  return activity;
}

export async function openPopulatedV3(page: Page, name: Name, theme: 'light' | 'dark', seed: Seed) {
  await page.clock.setFixedTime(new Date(fixedTime));
  await page.addInitScript(
    ({ token, theme }) => {
      sessionStorage.setItem('mingjing-auth-token', token);
      localStorage.setItem('mingjing-theme', theme);
    },
    { token: seed.token, theme },
  );
  const required: Record<Name, string[]> = {
    today: ['/api/chart', '/api/cases', '/api/history'],
    chat: ['/api/history'],
    chart: ['/api/chart'],
    tarot: [
      '/api/tarot/deck',
      '/api/tarot/draws',
      `/api/tarot/draws/${seed.drawId}`,
      `/api/tarot/draws/${seed.drawId}/readings`,
    ],
    cases: ['/api/cases'],
    me: ['/api/memories', '/api/subjects/self/profile'],
    settings: ['/api/reports/schedules', '/api/state', '/api/health'],
  };
  const arrivals = required[name].map((endpoint) =>
    page.waitForResponse(
      (response) =>
        new URL(response.url()).origin === frontend && new URL(response.url()).pathname === endpoint && response.ok(),
    ),
  );
  const route =
    name === 'tarot' ? `tarot?draw=${seed.drawId}` : name === 'chart' ? `chart?tab=bazi&date=${fixedDate}` : name;
  await page.goto(`/#/${route}`, { waitUntil: 'domcontentloaded' });
  await Promise.all(arrivals);
  await expect(page.locator(`[data-page="${name}"]`)).toBeVisible();
  if (name === 'today') {
    await expect(page.getByRole('heading', { name: seed.dayLabel, exact: true })).toBeVisible();
    await expect(page.getByText(/最近有 [1-9]\d* 条对话记录可继续查看/)).toBeVisible();
    await expect(page.getByRole('link', { name: new RegExp(seed.caseTitle) })).toBeVisible();
  }
  if (name === 'chat') {
    await expect(page.getByText('这是飞书上的合成历史。', { exact: true })).toBeVisible();
    await expect(page.getByRole('textbox', { name: '和明镜说说' })).toBeEnabled();
  }
  if (name === 'chart') {
    await expect(page.getByRole('button', { name: /^查看年柱[^—]+依据$/ })).toBeVisible();
    await expect(page.locator('.pillar-glyphs')).toHaveCount(4);
  }
  if (name === 'tarot') {
    await expect(page.getByRole('form', { name: '塔罗提问', exact: true })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: seed.question, exact: true })).toBeVisible();
    await expect(page.getByRole('article', { name: '第1版解读' })).toBeVisible();
    await expect(page.getByRole('button', { name: '重新解读 · 不换牌', exact: true })).toBeEnabled();
    await expect(page.getByRole('button', { name: '全部揭开', exact: true })).toHaveCount(0);
  }
  if (name === 'cases') await expect(page.getByRole('button', { name: new RegExp(seed.caseTitle) })).toBeVisible();
  if (name === 'me') {
    await expect(page.getByRole('heading', { name: '核对出生资料', exact: true })).toBeVisible();
    await expect(page.getByRole('textbox', { name: '阳历出生日期', exact: true })).not.toHaveValue('');
    await expect(page.getByText(/目前有 [1-9]\d* 条有效记忆/)).toBeVisible();
  }
  if (name === 'settings') {
    await expect(page.locator('[data-report-kind]')).toHaveCount(4);
    await expect(page.getByRole('button', { name: '保存晨报设置', exact: true })).toBeEnabled();
    await expect(page.getByRole('button', { name: '保存记忆设置', exact: true })).toBeEnabled();
    await expect(page.getByText('当前模型：尚未读取', { exact: true })).toHaveCount(0);
  }
  await expect(
    page.getByRole('status').filter({ hasText: /正在读取|正在核对有效记忆|正在恢复这次固定牌阵/ }),
  ).toHaveCount(0);
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForLoadState('networkidle');
}

export async function captureV3(
  page: Page,
  name: Name,
  theme: 'light' | 'dark',
  activity: Activity,
  readinessError = '',
) {
  const viewport = page.viewportSize()!;
  const id = `Q9-v3-${name}-${theme}-${viewport.width}`;
  const inspected = await inspectQ9(page);
  // Reuse the common rules while excluding user text and raw values from diagnostics.
  const inspection = {
    ...inspected,
    screens: inspected.screens.map((screen) => ({
      ...screen,
      cinnabar_uses: screen.cinnabar_uses.map((use) => ({ className: use.className, text: '' })),
    })),
    violations: inspected.violations.map((rule) => ({
      ...rule,
      nodes: rule.nodes.map((node) => ({ target: node.target, summary: undefined })),
    })),
  };
  await fs.mkdir(evidence, { recursive: true });
  const images = [];
  for (const fullPage of [false, true]) {
    const bytes = await page.screenshot({ fullPage, animations: 'disabled' });
    const filename = path.join(evidence, `${id}${fullPage ? '-full' : ''}.png`);
    await fs.writeFile(filename, bytes, { flag: 'wx' });
    images.push({ screenshot: repositoryPath(filename), sha256: digest(bytes), full_page: fullPage });
  }
  const manifest = await fs.readFile(path.resolve(webRoot, '../static/dist/.vite/manifest.json'));
  const audit = {
    schema: 'frontend-q9-v3-visual-v1',
    run_id: batch,
    id,
    mode: 'v3',
    page: name,
    viewport,
    theme,
    screenshot: images[0].screenshot,
    sha256: images[0].sha256,
    full_screenshot: images[1].screenshot,
    images,
    captured_at_beijing: beijingNow(),
    clock: fixedTime,
    build_manifest_sha256: digest(manifest),
    synthetic_only: true,
    backend: `${backend} / core_test_fe`,
    fixture_model: 'scripted-only, one reading preseeded per worker; no browser model trigger',
    checks: { ready: !readinessError, readiness_error: readinessError, inspection, boundary: activity },
  };
  await writeEvidence(`${id}.json`, audit);
  expect.soft(readinessError, 'The populated v3 readiness contract must pass before accepting a screenshot').toBe('');
  assertQ9Inspection(inspection, theme);
  expect(activity.external).toEqual([]);
  expect(activity.writes).toEqual([]);
  expect(activity.errors).toEqual([]);
  expect(activity.console).toEqual([]);
  expect(activity.failed).toEqual([]);
  expect(activity.expected_cancellations.length).toBeLessThanOrEqual(name === 'tarot' ? 1 : 0);
  expect(activity.http_errors).toEqual([]);
  return audit;
}
