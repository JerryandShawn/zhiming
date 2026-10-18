import { chromium, request } from '@playwright/test';
import fs from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';

const baseURL = 'http://127.0.0.1:4173';
const label = process.env.MINGJING_PERF_LABEL ?? 'final';
if (!/^[a-z0-9-]+$/.test(label)) throw new Error('Invalid evidence label');
const runs = Number(process.env.MINGJING_PERF_RUNS ?? 5);
if (!Number.isInteger(runs) || runs < 1 || runs > 10) throw new Error('Expected 1–10 runs');
const directory = `evidence/2026-10-18/components-m5/performance/${label}`;
await fs.mkdir(directory, { recursive: true });
const api = await request.newContext({ baseURL: 'http://127.0.0.1:8002' });
const owner = await api.post('/__test__/owner');
if (!owner.ok()) throw new Error('Synthetic owner could not be created');
const { token } = await owner.json();
const headers = { 'X-Token': token };
const state = await (await api.get('/api/state', { headers })).json();
const confirmed = await api.post('/api/subjects/self/profile/confirm', {
  headers,
  data: {
    request_id: crypto.randomUUID(),
    expected_revision: state.revision,
    confirmed: true,
    profile: {
      gender: '女',
      birth: {
        solar_datetime: '1998-03-12 08:15',
        precision: 'exact',
        timezone_offset: 8,
        location: { city: '合成地点', lng: 116.4, lat: 39.9 },
      },
    },
  },
});
if (!confirmed.ok()) throw new Error('Synthetic profile could not be confirmed');
const browser = await chromium.launch({ channel: process.env.CI ? undefined : 'chrome', headless: true });
const network = {
  offline: false,
  latency: 150,
  downloadThroughput: 200000,
  uploadThroughput: 93750,
  connectionType: 'cellular4g',
};
const results = [];
try {
  for (let run = 1; run <= runs; run++) {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      screen: { width: 390, height: 844 },
      deviceScaleFactor: 2,
      isMobile: true,
      hasTouch: true,
      serviceWorkers: 'block',
      locale: 'zh-CN',
      timezoneId: 'Asia/Shanghai',
      reducedMotion: 'no-preference',
    });
    await context.addInitScript((value) => {
      sessionStorage.setItem('mingjing-auth-token', value);
      localStorage.setItem('mingjing-theme', 'light');
      window.__frontendLcp = [];
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries())
          window.__frontendLcp.push({
            startTime: entry.startTime,
            renderTime: entry.renderTime,
            loadTime: entry.loadTime,
            size: entry.size,
            element: entry.element
              ? {
                  tag: entry.element.tagName,
                  id: entry.element.id,
                  class: entry.element.className,
                  text: entry.element.textContent?.slice(0, 100),
                }
              : null,
          });
      }).observe({ type: 'largest-contentful-paint', buffered: true });
    }, token);
    const page = await context.newPage();
    const cdp = await context.newCDPSession(page);
    await cdp.send('Network.enable');
    await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
    await cdp.send('Network.clearBrowserCache');
    await cdp.send('Network.emulateNetworkConditions', network);
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
    const errors = [],
      external = [],
      responseHeaders = [],
      pendingHeaders = [];
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('request', (event) => {
      const url = new URL(event.url());
      if (['https:', 'http:'].includes(url.protocol) && url.origin !== baseURL) external.push(url.origin);
    });
    page.on('response', (response) =>
      pendingHeaders.push(
        (async () => {
          responseHeaders.push({
            path: new URL(response.url()).pathname,
            status: response.status(),
            encoding: await response.headerValue('content-encoding'),
          });
        })(),
      ),
    );
    const chartResponse = page.waitForResponse(
      (response) => new URL(response.url()).pathname === '/api/chart' && response.ok(),
    );
    await page.goto(`${baseURL}/#/today`, { waitUntil: 'load', timeout: 60000 });
    await page.locator('[data-page="today"]').waitFor();
    await chartResponse;
    await page.getByText(/^最近有 \d+ 条对话记录可继续查看。$/).waitFor();
    await page.evaluate(() => document.fonts.ready);
    await page.waitForLoadState('networkidle');
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const sample = await page.evaluate(() => ({
      lcp_entries: window.__frontendLcp,
      resources: performance.getEntriesByType('resource').map((entry) => ({
        path: new URL(entry.name).pathname,
        start: entry.startTime,
        responseEnd: entry.responseEnd,
        duration: entry.duration,
        transferSize: entry.transferSize,
        encodedBodySize: entry.encodedBodySize,
        decodedBodySize: entry.decodedBodySize,
        initiatorType: entry.initiatorType,
      })),
      navigation: performance.getEntriesByType('navigation').map((entry) => entry.toJSON()),
      login_dialogs: document.querySelectorAll('.login-dialog').length,
      day_heading: document.querySelector('[data-page="today"] .section h3')?.textContent,
    }));
    await Promise.all(pendingHeaders);
    if (!sample.lcp_entries.length || sample.login_dialogs || !sample.day_heading || errors.length || external.length)
      throw new Error('Measurement did not finish on the populated, authenticated local Today page');
    const lcp = sample.lcp_entries.at(-1).startTime;
    const screenshot = `${directory}/run-${run}.png`;
    await page.screenshot({ path: screenshot, animations: 'allow' });
    results.push({
      run,
      lcp_ms: lcp,
      ...sample,
      response_headers: responseHeaders,
      errors,
      external,
      screenshot: `web/${screenshot}`,
    });
    console.log(
      JSON.stringify({
        run,
        lcp_ms: lcp,
        element: sample.lcp_entries.at(-1).element,
        font_requests: sample.resources.filter((entry) => entry.path.endsWith('.woff2')).length,
      }),
    );
    await context.close();
  }
} finally {
  await browser.close();
}
const metrics = await (await api.get('/__test__/metrics')).json();
await api.dispose();
if (metrics.database !== 'core_test_fe' || metrics.real_model_calls !== 0) throw new Error('Fixture isolation failed');
const sorted = results.map((value) => value.lcp_ms).sort((a, b) => a - b);
const p75 = sorted[Math.ceil(sorted.length * 0.75) - 1];
const manifest = JSON.parse(await fs.readFile('../static/dist/.vite/manifest.json', 'utf8'));
const build = {};
const hashFile = async (filename) =>
  createHash('sha256')
    .update(await fs.readFile(filename))
    .digest('hex');
for (const name of await fs.readdir('../static/dist/assets')) {
  if (!/\.(js|css)$/.test(name)) continue;
  build[`static/dist/assets/${name}`] = createHash('sha256')
    .update(await fs.readFile(`../static/dist/assets/${name}`))
    .digest('hex');
}
for (const name of ['index.html', '.vite/manifest.json', 'fonts/fonts.css', 'fonts/manifest.json'])
  build[`static/dist/${name}`] = await hashFile(`../static/dist/${name}`);
for (const name of new Set(
  results.flatMap((result) =>
    result.resources.filter((entry) => entry.path.endsWith('.woff2')).map((entry) => entry.path),
  ),
))
  build[`static/dist${name}`] = await hashFile(`../static/dist${name}`);
const sourceHashes = {};
async function fingerprint(directory) {
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    const name = `${directory}/${entry.name}`;
    if (entry.isDirectory()) await fingerprint(name);
    else if (/\.(tsx?|css|svg)$/.test(entry.name)) sourceHashes[`web/${name}`] = await hashFile(name);
  }
}
await fingerprint('src');
for (const name of ['scripts/measure-mobile-lcp.mjs', 'scripts/prepare-fonts.mjs', 'index.html', 'vite.config.ts'])
  sourceHashes[`web/${name}`] = await hashFile(name);
const report = {
  captured_at: new Date().toISOString(),
  label,
  commit_at_measurement: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
  browser: browser.version(),
  node: process.version,
  route: '/#/today',
  mode: 'built-live-page-synthetic-PG-data',
  viewport: { width: 390, height: 844, deviceScaleFactor: 2, mobile: true, touch: true },
  network,
  cpu_slowdown: 4,
  cache_disabled: true,
  fresh_context_each_run: true,
  service_workers: 'blocked',
  normal_motion: true,
  target_ms: 2500,
  p75_ms: p75,
  all_runs_below_target: sorted.every((value) => value < 2500),
  final_acceptance_sample: runs >= 5,
  fixture: { database: metrics.database, model: metrics.model, real_model_calls: metrics.real_model_calls },
  build_hashes: build,
  source_hashes: sourceHashes,
  manifest,
  results,
};
await fs.writeFile(`${directory}/report.json`, JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ label, runs, p75_ms: p75, all_runs_below_target: report.all_runs_below_target }));
if (label === 'final' && (!report.final_acceptance_sample || !report.all_runs_below_target)) process.exitCode = 1;
