import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { safeWebPath, webRoot } from './bundle-budget.mjs';

// A real loopback HTTP server preserves CDP network throttling. Browser route.fulfill
// would bypass the transfer time we are trying to measure. No database/model is used.
const root = path.resolve(webRoot, '..');
const target = process.env.FRONTEND_PERF_TARGET ?? 'legacy';
if (!['legacy', 'h5', 'courses'].includes(target)) throw new Error('Expected legacy, h5 or courses target');
const builtTarget = target !== 'legacy';
const runs = Number(process.env.FRONTEND_PERF_RUNS ?? 5);
if (![1, 5].includes(runs)) throw new Error('Expected one diagnostic run or five acceptance runs');
const diagnostic = runs === 1;
const encoding = process.env.FRONTEND_PERF_ENCODING ?? 'identity';
if (!['identity', 'gzip'].includes(encoding)) throw new Error('Expected identity or gzip delivery');
const attempt = process.env.LEGACY_PERF_ATTEMPT;
if (!attempt || !/^[a-z0-9][a-z0-9_-]{0,47}$/i.test(attempt)) throw new Error('Choose a fresh safe attempt name');
const directory = await safeWebPath(`evidence/2026-10-27/${target}-performance/${attempt}`);
await fs.mkdir(path.dirname(directory), { recursive: true });
await fs.mkdir(directory, { recursive: false });
const harnessBytes = await fs.readFile(fileURLToPath(import.meta.url));
await fs.writeFile(path.join(directory, 'harness.mjs'), harnessBytes);
const bjt = () => new Date(Date.now() + 28800000).toISOString().replace('Z', '+08:00');
const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim();
const hash = (value) => createHash('sha256').update(value).digest('hex');
const runtimePaths = ['static/index.html', 'static/app.js', 'static/base.css', 'static/paper.css'];
const buildPaths = [
  'web/vite.config.ts',
  'web/compression.plugin.ts',
  'web/pwa.plugin.ts',
  'web/index.html',
  'web/package.json',
  'web/package-lock.json',
  'web/scripts/prepare-fonts.mjs',
  'web/scripts/font-css.mjs',
];
async function provenance() {
  const files = {};
  async function visit(relative) {
    for (const entry of await fs.readdir(path.join(root, relative), { withFileTypes: true })) {
      const name = `${relative}/${entry.name}`;
      if (entry.isDirectory()) await visit(name);
      else if (entry.isFile()) files[name] = hash(await fs.readFile(path.join(root, name)));
    }
  }
  for (const file of runtimePaths) files[file] = hash(await fs.readFile(path.join(root, file)));
  await visit('static/dist');
  await visit('static/vendor');
  if (builtTarget) {
    await visit('web/src');
    await visit('web/public');
    for (const file of buildPaths) files[file] = hash(await fs.readFile(path.join(root, file)));
  }
  return {
    head: git('rev-parse', 'HEAD'),
    font_display_modes: builtTarget
      ? [
          ...new Set(
            [
              ...(await fs.readFile(path.join(root, 'web/public/fonts/fonts.css'), 'utf8')).matchAll(
                /font-display:([a-z]+)/g,
              ),
            ].map((match) => match[1]),
          ),
        ]
      : [],
    runtime_dirty: Boolean(
      git('status', '--porcelain', '--', ...runtimePaths, 'web/src', 'web/public', ...(builtTarget ? buildPaths : [])),
    ),
    files,
  };
}
const fixture = {
  '/api/sessions': [{ id: 'shared', title: '合成性能对话' }],
  '/api/health': { ok: true },
  '/api/state': { revision: 1, facts: [], cases: [], settings: {} },
  '/api/history': [],
  '/api/cases': [],
  '/api/memories': [],
  '/api/archive': {},
};
const methods = [],
  unexpected = [];
const types = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.png': 'image/png',
  '.json': 'application/json',
  '.webmanifest': 'application/manifest+json',
};
const server = http.createServer(async (request, response) => {
  try {
    const url = new URL(request.url, 'http://127.0.0.1');
    methods.push(request.method);
    response.setHeader('Cache-Control', 'no-store');
    if (request.method !== 'GET') {
      unexpected.push({ method: request.method, path: url.pathname });
      response.writeHead(405).end();
      return;
    }
    if (url.pathname.startsWith('/api/')) {
      if (builtTarget || !Object.hasOwn(fixture, url.pathname)) unexpected.push({ method: 'GET', path: url.pathname });
      response.writeHead(200, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify(fixture[url.pathname] ?? {}));
      return;
    }
    if (url.pathname === '/favicon.ico') return void response.writeHead(204).end();
    const filename = builtTarget
      ? path.resolve(root, 'static/dist', url.pathname === '/' ? 'index.html' : '.' + decodeURIComponent(url.pathname))
      : url.pathname === '/'
        ? path.join(root, 'static/index.html')
        : path.resolve(root, '.' + decodeURIComponent(url.pathname));
    if (!filename.startsWith(path.join(root, 'static') + path.sep)) return void response.writeHead(404).end();
    let bytes = await fs.readFile(filename),
      compressed = false;
    if (encoding === 'gzip' && /\bgzip\b/.test(request.headers['accept-encoding'] ?? '')) {
      try {
        bytes = await fs.readFile(filename + '.gz');
        compressed = true;
      } catch (error) {
        if (error.code !== 'ENOENT') throw error;
      }
    }
    response.setHeader('Vary', 'Accept-Encoding');
    if (compressed) response.setHeader('Content-Encoding', 'gzip');
    response.writeHead(200, {
      'Content-Type': types[path.extname(filename)] ?? 'application/octet-stream',
      'Content-Length': bytes.length,
    });
    response.end(bytes);
  } catch {
    response.writeHead(404).end();
  }
});
await new Promise((resolve, reject) => {
  server.once('error', reject);
  server.listen(0, '127.0.0.1', resolve);
});
const origin = `http://127.0.0.1:${server.address().port}`;
const network = {
  offline: false,
  latency: 150,
  downloadThroughput: 200000,
  uploadThroughput: 100000,
  connectionType: 'cellular4g',
};
const batch = {
  encoding_mode: encoding,
  started_bjt: bjt(),
  mode:
    target === 'courses'
      ? 'courses-pinned-synthetic-study-built-loopback-http-no-api'
      : target === 'h5'
        ? 'h5-isolated-demo-built-loopback-http-no-api'
        : 'old-html-built-module-loopback-http-synthetic-read-only-api',
  network,
  cpu_slowdown: 4,
  runs,
  diagnostic_only: diagnostic,
};
await fs.writeFile(path.join(directory, 'batch.json'), JSON.stringify({ ...batch, status: 'running' }, null, 2));
let browser;
try {
  const before = await provenance();
  browser = await chromium.launch({ channel: process.env.CI ? undefined : 'chrome', headless: true });
  const samples = [];
  for (let run = 1; run <= runs; run++) {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 2,
      isMobile: true,
      hasTouch: true,
      locale: 'zh-CN',
      timezoneId: 'Asia/Shanghai',
      serviceWorkers: 'block',
      reducedMotion: 'no-preference',
    });
    const outside = [],
      errors = [],
      failures = [];
    await context.route(
      (url) => ['http:', 'https:'].includes(url.protocol) && url.origin !== origin,
      (route) => {
        outside.push(new URL(route.request().url()).origin);
        return route.abort();
      },
    );
    await context.addInitScript((target) => {
      if (target === 'legacy') localStorage.setItem('mjt_token', 'synthetic-performance-token');
      else localStorage.setItem('mingjing-theme', 'light');
      window.__legacyLcp = [];
      window.__courseReady = null;
      if (target === 'courses') {
        const ready = new MutationObserver(() => {
          if (document.querySelector('[data-course-state="ready"]')) {
            window.__courseReady = performance.now();
            ready.disconnect();
          }
        });
        ready.observe(document, {
          childList: true,
          subtree: true,
          attributes: true,
          attributeFilter: ['data-course-state'],
        });
      }
      const capture = (entries) =>
        entries.forEach((entry) =>
          window.__legacyLcp.push({
            startTime: entry.startTime,
            size: entry.size,
            element: entry.element?.tagName ?? null,
            class_name: String(entry.element?.className ?? '').slice(0, 180),
            parent_class: String(entry.element?.parentElement?.className ?? '').slice(0, 180),
            text_length: entry.element?.textContent?.length ?? 0,
          }),
        );
      const observer = new PerformanceObserver((list) => capture(list.getEntries()));
      observer.observe({ type: 'largest-contentful-paint', buffered: true });
      window.__legacyLcpFlush = () => capture(observer.takeRecords());
    }, target);
    const page = await context.newPage();
    page.on('pageerror', () => errors.push('pageerror'));
    page.on('response', (response) => {
      if (response.status() >= 400)
        failures.push({ path: new URL(response.url()).pathname, status: response.status() });
    });
    const cdp = await context.newCDPSession(page);
    await cdp.send('Network.enable');
    await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
    await cdp.send('Network.clearBrowserCache');
    await cdp.send('Network.emulateNetworkConditions', network);
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
    try {
      const route =
        target === 'courses'
          ? '/?spaces=demo#/chat?space=study&topic=chart-study&view=courses'
          : target === 'h5'
            ? '/?embed=demo#/chat'
            : '/#/chat';
      await page.goto(origin + route, { waitUntil: 'networkidle' });
      if (target === 'legacy') await page.waitForFunction(() => Boolean(window.mingjingLegacyStream));
      else if (target === 'h5') await page.locator('[data-demo="h5"]').waitFor();
      else await page.locator('[data-course-state="ready"]').waitFor();
      if (target !== 'courses')
        await page.getByRole('textbox', { name: target === 'h5' ? '本地草稿' : '本次问题' }).waitFor();
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(1000);
      const timings = await page.evaluate(() => {
        window.__legacyLcpFlush();
        return {
          entries: window.__legacyLcp,
          course_ready_ms: window.__courseReady,
          first_contentful_paint_ms: performance.getEntriesByName('first-contentful-paint')[0]?.startTime ?? null,
          resources: performance.getEntriesByType('resource').map((entry) => ({
            path: new URL(entry.name).pathname,
            transfer_size: entry.transferSize,
            duration: entry.duration,
            start_time: entry.startTime,
            response_end: entry.responseEnd,
            encoded_body_size: entry.encodedBodySize,
            decoded_body_size: entry.decodedBodySize,
            initiator_type: entry.initiatorType,
          })),
        };
      });
      const lcp = timings.entries.at(-1)?.startTime;
      if (!Number.isFinite(lcp) || !lcp) throw new Error('No LCP measurement');
      await page.screenshot({ path: path.join(directory, `cold-${run}.png`), fullPage: true });
      samples.push({ run, lcp_ms: lcp, ...timings, outside, errors, failures });
      console.log(JSON.stringify({ run, lcp_ms: lcp }));
    } finally {
      await context.close();
    }
  }
  const after = await provenance();
  const harnessStable = harnessBytes.equals(await fs.readFile(fileURLToPath(import.meta.url)));
  const stable = JSON.stringify(before) === JSON.stringify(after) && harnessStable;
  const sorted = samples.map((sample) => sample.lcp_ms).sort((a, b) => a - b);
  const passed =
    !diagnostic &&
    stable &&
    !before.runtime_dirty &&
    sorted.every((value) => value < 2500) &&
    !unexpected.length &&
    samples.every((sample) => !sample.errors.length && !sample.outside.length && !sample.failures.length);
  const report = {
    ...batch,
    finished_bjt: bjt(),
    browser: browser.version(),
    node: process.version,
    before,
    after,
    runtime_stable: stable,
    harness_sha256: hash(harnessBytes),
    harness_snapshot: 'harness.mjs',
    harness_stable: harnessStable,
    harness_tracked_status: git('status', '--porcelain', '--', 'web/scripts/measure-legacy-lcp.mjs'),
    cache_disabled: true,
    fresh_context_each_run: true,
    viewport: { width: 390, height: 844, deviceScaleFactor: 2 },
    p75_ms: diagnostic ? null : sorted[3],
    target_ms: 2500,
    passed,
    methods: [...new Set(methods)],
    unexpected,
    samples,
    limitations:
      target === 'courses'
        ? 'Synthetic fixed course deep link only; not personal study progress, signed-in Today, real API, device or deployment acceptance.'
        : target === 'h5'
          ? 'Isolated H5 sign-in demo only, not signed-in Today, real Feishu/cookie authentication, device, API or deployment acceptance.'
          : 'Synthetic read-only HTTP fixture, not P4 HTTP+PG, new P10 page, real device, deployment or server measurement.',
  };
  await fs.writeFile(path.join(directory, 'report.json'), JSON.stringify(report, null, 2));
  await fs.writeFile(
    path.join(directory, 'batch.json'),
    JSON.stringify(
      { ...batch, status: diagnostic ? 'diagnostic_completed' : passed ? 'passed' : 'failed', finished_bjt: bjt() },
      null,
      2,
    ),
  );
  console.log(
    JSON.stringify({ passed, diagnostic_only: diagnostic, p75_ms: diagnostic ? null : sorted[3], directory }),
  );
  if (!passed && !diagnostic) process.exitCode = 1;
} catch (error) {
  await fs.writeFile(
    path.join(directory, 'batch.json'),
    JSON.stringify({ ...batch, status: 'failed', finished_bjt: bjt(), failure: error.name }, null, 2),
  );
  throw error;
} finally {
  if (browser) await browser.close();
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));
}
