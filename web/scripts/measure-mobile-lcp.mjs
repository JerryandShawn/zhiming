import { chromium, request } from '@playwright/test';
import fs from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { calculateBundleBudget, safeWebPath, webRoot } from './bundle-budget.mjs';

const baseURL = 'http://127.0.0.1:4173';
const label = process.env.MINGJING_PERF_LABEL ?? 'final';
if (!['baseline', 'font', 'route', 'final'].includes(label))
  throw new Error('Expected baseline/font/route/final label');
const acceptanceFlag = process.env.MINGJING_PERF_ACCEPTANCE ?? '1';
if (!['0', '1'].includes(acceptanceFlag)) throw new Error('MINGJING_PERF_ACCEPTANCE must be 0 or 1');
const acceptance = acceptanceFlag === '1';
const runs = Number(process.env.MINGJING_PERF_RUNS ?? 5);
if (!Number.isInteger(runs) || runs < 1 || runs > 10) throw new Error('Expected 1–10 runs');
if (acceptance && runs < 5) throw new Error('Acceptance requires at least five cold runs regardless of label');
const attempt = process.env.MINGJING_PERF_ATTEMPT;
if (
  attempt !== undefined &&
  (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$/.test(attempt) || /^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(attempt))
)
  throw new Error('MINGJING_PERF_ATTEMPT must be a safe 1–48 character name');
const directory = await safeWebPath(
  path.join(
    process.env.MINGJING_PERF_EVIDENCE_DIR ?? 'evidence/2026-10-18/components-m5/performance',
    label,
    attempt ?? '',
  ),
);
const reportPath = path.join(directory, 'report.json');
try {
  await fs.stat(reportPath);
  throw new Error('Existing performance report preserved; choose a fresh MINGJING_PERF_ATTEMPT');
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
}
await fs.mkdir(directory, { recursive: true });
const bjt = () => new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString().replace('Z', '+08:00');
const git = (args) => execFileSync('git', args, { cwd: webRoot, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 }).trim();
const hashFile = async (filename) =>
  createHash('sha256')
    .update(await fs.readFile(filename))
    .digest('hex');
async function fingerprint(root, prefix) {
  const hashes = {};
  async function visit(directory) {
    for (const entry of (await fs.readdir(directory, { withFileTypes: true })).sort((a, b) =>
      a.name.localeCompare(b.name),
    )) {
      const location = path.join(directory, entry.name);
      if (entry.isDirectory()) await visit(location);
      else if (entry.isFile())
        hashes[`${prefix}/${path.relative(root, location).replaceAll('\\', '/')}`] = await hashFile(location);
    }
  }
  await visit(root);
  return hashes;
}
const sourcePaths = [
  'src',
  'public',
  'scripts',
  'index.html',
  'vite.config.ts',
  'pwa.plugin.ts',
  'package.json',
  'package-lock.json',
];
async function provenance() {
  const sources = {};
  for (const name of sourcePaths) {
    const location = path.resolve(webRoot, name),
      stat = await fs.stat(location);
    if (stat.isDirectory()) Object.assign(sources, await fingerprint(location, `web/${name}`));
    else sources[`web/${name}`] = await hashFile(location);
  }
  const status = git(['status', '--porcelain=v1', '--untracked-files=all', '--', ...sourcePaths]);
  const diff = git(['diff', '--binary', 'HEAD', '--', ...sourcePaths]);
  return {
    captured_time_bjt: bjt(),
    base_HEAD: git(['rev-parse', 'HEAD']),
    dirty: Boolean(status),
    dirty_status: status.split('\n').filter(Boolean),
    dirty_diff_sha256: createHash('sha256').update(diff).digest('hex'),
    source_hashes: sources,
    build_hashes: await fingerprint(path.resolve(webRoot, '../static/dist'), 'static/dist'),
  };
}
const batchPath = path.join(directory, 'batch.json');
const batch = { label, attempt, started_time_bjt: bjt(), acceptance_requested: acceptance, requested_runs: runs };
await fs.writeFile(batchPath, JSON.stringify({ ...batch, status: 'running' }, null, 2) + '\n', { flag: 'wx' });
let batchPhase = 'provenance',
  currentRun = 0,
  api,
  browser;
const results = [];
try {
  const before = await provenance(),
    bundle = await calculateBundleBudget();
  batchPhase = 'fixture-setup';
  api = await request.newContext({ baseURL: 'http://127.0.0.1:8002' });
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
  batchPhase = 'browser-setup';
  browser = await chromium.launch({ channel: process.env.CI ? undefined : 'chrome', headless: true });
  const network = {
    offline: false,
    latency: 150,
    downloadThroughput: 200000,
    uploadThroughput: 93750,
    connectionType: 'cellular4g',
  };
  try {
    for (let run = 1; run <= runs; run++) {
      currentRun = run;
      batchPhase = 'cold-run';
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
        const capture = (entries) => {
          for (const entry of entries)
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
                  }
                : null,
            });
        };
        const observer = new PerformanceObserver((list) => capture(list.getEntries()));
        observer.observe({ type: 'largest-contentful-paint', buffered: true });
        window.__frontendLcpFlush = () => capture(observer.takeRecords());
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
        networkRequests = new Map(),
        responseHeaders = [],
        pendingHeaders = [];
      page.on('pageerror', (error) => errors.push(error.message));
      cdp.on('Network.requestWillBeSent', (event) => {
        const url = new URL(event.request.url);
        networkRequests.set(event.requestId, {
          path: ['http:', 'https:'].includes(url.protocol) ? url.pathname : '[non-http-resource]',
          type: event.type,
          encoded_network_bytes: 0,
          completed: false,
        });
      });
      cdp.on('Network.loadingFinished', (event) => {
        const entry = networkRequests.get(event.requestId);
        if (entry) Object.assign(entry, { encoded_network_bytes: event.encodedDataLength, completed: true });
      });
      cdp.on('Network.loadingFailed', (event) => {
        const entry = networkRequests.get(event.requestId);
        if (entry) Object.assign(entry, { failed: event.errorText });
      });
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
      let phase = 'navigation',
        chartReceipt,
        dataReceipt;
      try {
        const waitForGet = (pathname) =>
          page.waitForResponse(
            (response) => {
              const url = new URL(response.url());
              return response.request().method() === 'GET' && url.origin === baseURL && url.pathname === pathname;
            },
            { timeout: 90000 },
          );
        const [chartResponse, historyResponse, casesResponse] = await Promise.all([
          waitForGet('/api/chart'),
          waitForGet('/api/history'),
          waitForGet('/api/cases'),
          page.goto(`${baseURL}/#/today`, { waitUntil: 'load', timeout: 90000 }),
        ]);
        phase = 'today-data-http';
        const [chartBody, historyBody, casesBody] = await Promise.all(
          [chartResponse, historyResponse, casesResponse].map((response) => response.json().catch(() => null)),
        );
        chartReceipt = {
          status: chartResponse.status(),
          code:
            typeof chartBody?.code === 'string' && /^[A-Z0-9_]{1,64}$/.test(chartBody.code)
              ? chartBody.code
              : undefined,
          chart_dependency_missing:
            typeof chartBody?.detail === 'string' && chartBody.detail.includes('missing_chart_dependency'),
        };
        dataReceipt = { history_status: historyResponse.status(), cases_status: casesResponse.status() };
        if (![chartResponse, historyResponse, casesResponse].every((response) => response.ok()))
          throw new Error('Today data request failed');
        phase = 'today-data-payload';
        if (!Array.isArray(historyBody) || !Array.isArray(casesBody)) throw new Error('Today lists must be arrays');
        const historyCount = historyBody.length,
          casesCount = casesBody.length,
          openCasesCount = casesBody.filter((item) => item?.status === 'open').length,
          displayedCasesCount = Math.min(openCasesCount, 5);
        Object.assign(dataReceipt, {
          history_count: historyCount,
          cases_count: casesCount,
          open_cases_count: openCasesCount,
        });
        const dayLabel = typeof chartBody?.day?.day_ganzhi === 'string' ? chartBody.day.day_ganzhi.trim() : '';
        if (!dayLabel || dayLabel === '流日字段尚未提供') throw new Error('Chart day.day_ganzhi is missing');
        phase = 'populated-ui';
        await page.locator('[data-page="today"]').waitFor({ timeout: 90000 });
        await page.waitForFunction(
          ({ dayLabel, historyCount, displayedCasesCount }) => {
            const today = document.querySelector('[data-page="today"]');
            if (!today || today.querySelector('.error-banner')) return false;
            if ([...today.querySelectorAll('[role="status"]')].some((node) => node.textContent?.includes('正在读取')))
              return false;
            const sections = [...today.querySelectorAll('.section')];
            const history = sections.find((node) => node.querySelector('h2')?.textContent?.trim() === '最近对话');
            const cases = sections.find((node) => node.querySelector('h2')?.textContent?.trim() === '进行中的事');
            const historyText = historyCount ? `最近有 ${historyCount} 条对话记录可继续查看。` : '还没有对话记录。';
            return (
              today.querySelector('.section h3')?.textContent?.trim() === dayLabel &&
              [...(history?.querySelectorAll('p') ?? [])].some((node) => node.textContent?.trim() === historyText) &&
              cases?.querySelectorAll('.row-link').length === displayedCasesCount &&
              (displayedCasesCount > 0 ||
                [...cases.querySelectorAll('p')].some((node) => node.textContent?.trim() === '暂无进行中的事项。'))
            );
          },
          { dayLabel, historyCount, displayedCasesCount },
          { timeout: 90000 },
        );
        phase = 'fonts-and-network';
        await page.evaluate(() => document.fonts.ready);
        await page.waitForLoadState('networkidle');
        await page.evaluate(
          () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
        );
        const sample = await page.evaluate(() => {
          window.__frontendLcpFlush();
          const today = document.querySelector('[data-page="today"]');
          const sections = [...(today?.querySelectorAll('.section') ?? [])];
          const history = sections.find((node) => node.querySelector('h2')?.textContent?.trim() === '最近对话');
          const cases = sections.find((node) => node.querySelector('h2')?.textContent?.trim() === '进行中的事');
          const historyText = [...(history?.querySelectorAll('p') ?? [])].map((node) => node.textContent?.trim());
          const historyMatch = historyText
            .map((value) => /^最近有 (\d+) 条对话记录可继续查看。$/.exec(value ?? ''))
            .find(Boolean);
          return {
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
            today_error_banners: today?.querySelectorAll('.error-banner').length ?? 0,
            today_loading_states: [...(today?.querySelectorAll('[role="status"]') ?? [])].filter((node) =>
              node.textContent?.includes('正在读取'),
            ).length,
            rendered_history_count: historyMatch
              ? Number(historyMatch[1])
              : historyText.includes('还没有对话记录。')
                ? 0
                : null,
            rendered_cases_count: cases?.querySelectorAll('.row-link').length ?? null,
            cases_empty: [...(cases?.querySelectorAll('p') ?? [])].some(
              (node) => node.textContent?.trim() === '暂无进行中的事项。',
            ),
          };
        });
        await Promise.all(pendingHeaders);
        phase = 'validation';
        if (
          !sample.lcp_entries.length ||
          sample.login_dialogs ||
          sample.day_heading?.trim() !== dayLabel ||
          sample.today_error_banners ||
          sample.today_loading_states ||
          sample.rendered_history_count !== historyCount ||
          sample.rendered_cases_count !== displayedCasesCount ||
          (displayedCasesCount === 0 && !sample.cases_empty) ||
          errors.length ||
          external.length
        )
          throw new Error('Measurement did not finish on the populated, authenticated local Today page');
        const lcp = sample.lcp_entries.at(-1).startTime;
        const screenshot = `${directory}/run-${run}.png`;
        await page.screenshot({ path: screenshot, animations: 'allow' });
        const group = (predicate) => {
          const entries = sample.resources.filter(predicate),
            transfers = [...networkRequests.values()].filter(predicate);
          return {
            requests: entries.length,
            cdp_requests: transfers.length,
            failed_requests: transfers
              .filter((item) => item.failed)
              .map((item) => ({ path: item.path, error: item.failed })),
            transfer_bytes: entries.reduce((sum, item) => sum + item.transferSize, 0),
            encoded_body_bytes: entries.reduce((sum, item) => sum + item.encodedBodySize, 0),
            decoded_body_bytes: entries.reduce((sum, item) => sum + item.decodedBodySize, 0),
            cdp_network_bytes: transfers.reduce((sum, item) => sum + item.encoded_network_bytes, 0),
          };
        };
        const staticFiles = new Set(bundle.files.map((file) => `/${file.file}`));
        const observedMissing = sample.resources
          .filter((item) => /\.(?:js|css)$/.test(item.path) && !staticFiles.has(item.path))
          .map((item) => item.path);
        if (observedMissing.length)
          throw new Error(`Bundle closure omitted observed JS/CSS: ${observedMissing.join(', ')}`);
        const staticResource = (item) => /\.(?:js|css|woff2?|ttf|otf)$/.test(item.path);
        const resourceFailures = [
          ...[...networkRequests.values()]
            .filter(
              (item) => item.failed && (staticResource(item) || ['Script', 'Stylesheet', 'Font'].includes(item.type)),
            )
            .map((item) => ({ path: item.path, error: item.failed })),
          ...responseHeaders
            .filter((item) => item.status >= 400 && staticResource(item))
            .map((item) => ({ path: item.path, status: item.status })),
        ];
        results.push({
          run,
          lcp_ms: lcp,
          ...sample,
          chart_receipt: { ...chartReceipt, day_ganzhi: dayLabel, matches_ui: true },
          data_receipt: { ...dataReceipt, displayed_cases_count: displayedCasesCount, matches_ui: true },
          response_headers: responseHeaders,
          errors,
          external,
          javascript: group((item) => item.path.endsWith('.js')),
          fonts: group((item) => /\.(?:woff2?|ttf|otf)$/.test(item.path)),
          static_resource_failures: resourceFailures,
          network_requests: [...networkRequests.values()],
          screenshot: `web/${path.relative(webRoot, screenshot).replaceAll('\\', '/')}`,
        });
        console.log(
          JSON.stringify({
            run,
            lcp_ms: lcp,
            element: sample.lcp_entries.at(-1).element,
            font_requests: sample.resources.filter((entry) => entry.path.endsWith('.woff2')).length,
          }),
        );
      } catch {
        const screenshot = path.join(directory, `run-${run}-failed.png`);
        const snapshot = await page
          .evaluate(() => ({
            on_expected_route: location.hash === '#/today',
            today_present: Boolean(document.querySelector('[data-page="today"]')),
            login_dialogs: document.querySelectorAll('.login-dialog').length,
            auth_hidden: Boolean(document.querySelector('.auth-hidden')),
            day_heading: document.querySelector('[data-page="today"] .section h3')?.textContent,
            lcp_timings: (window.__frontendLcp ?? []).map(({ startTime, size }) => ({ startTime, size })),
          }))
          .catch(() => ({ document_unavailable: true }));
        await page
          .screenshot({ path: screenshot, timeout: 10000, mask: [page.locator('input, textarea')] })
          .catch(() => undefined);
        await Promise.allSettled(pendingHeaders);
        const diagnostic = {
          captured_time_bjt: bjt(),
          label,
          run,
          phase,
          base_HEAD: before.base_HEAD,
          chart_receipt: chartReceipt,
          data_receipt: dataReceipt,
          snapshot,
          responses: responseHeaders,
          network_requests: [...networkRequests.values()],
          page_error_count: errors.length,
          outside_request_count: external.length,
          screenshot: `web/${path.relative(webRoot, screenshot).replaceAll('\\', '/')}`,
        };
        await fs.writeFile(path.join(directory, `run-${run}-failed.json`), JSON.stringify(diagnostic, null, 2) + '\n');
        throw new Error(
          `Cold run ${run} failed at ${phase}${chartReceipt ? `: HTTP ${chartReceipt.status}${chartReceipt.code ? ` (${chartReceipt.code})` : ''}` : ''}; see run-${run}-failed.json`,
        );
      } finally {
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
  batchPhase = 'fixture-isolation';
  const metrics = await (await api.get('/__test__/metrics')).json();
  await api.dispose();
  api = undefined;
  if (metrics.database !== 'core_test_fe' || metrics.real_model_calls !== 0)
    throw new Error('Fixture isolation failed');
  const sorted = results.map((value) => value.lcp_ms).sort((a, b) => a - b);
  const p75 = sorted[Math.ceil(sorted.length * 0.75) - 1];
  batchPhase = 'final-provenance';
  const after = await provenance();
  const stable =
    JSON.stringify(before.source_hashes) === JSON.stringify(after.source_hashes) &&
    JSON.stringify(before.build_hashes) === JSON.stringify(after.build_hashes) &&
    before.base_HEAD === after.base_HEAD;
  const report = {
    captured_at: new Date().toISOString(),
    captured_time_bjt: bjt(),
    label,
    attempt,
    commit_at_measurement: before.base_HEAD,
    base_HEAD: before.base_HEAD,
    acceptance_requested: acceptance,
    provenance_before: before,
    provenance_after: after,
    immutable_build_and_source_during_measurement: stable,
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
    static_resources_loaded: results.every((value) => value.static_resource_failures.length === 0),
    final_acceptance_sample: acceptance && runs >= 5,
    fixture: { database: metrics.database, model: metrics.model, real_model_calls: metrics.real_model_calls },
    build_hashes: before.build_hashes,
    source_hashes: before.source_hashes,
    bundle_budget: bundle,
    manifest: bundle.manifest,
    results,
  };
  batchPhase = 'report-write';
  await fs.writeFile(reportPath, JSON.stringify(report, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify({ label, runs, p75_ms: p75, all_runs_below_target: report.all_runs_below_target }));
  const failed =
    !stable ||
    !report.static_resources_loaded ||
    (acceptance && (!report.final_acceptance_sample || !report.all_runs_below_target || !bundle.passed));
  await fs.writeFile(
    batchPath,
    JSON.stringify(
      {
        ...batch,
        status: failed ? 'failed' : acceptance ? 'passed' : 'measured',
        finished_time_bjt: bjt(),
        completed_runs: results.length,
        phase: failed ? 'validation' : 'complete',
        report: 'report.json',
      },
      null,
      2,
    ) + '\n',
  );
  if (failed) process.exitCode = 1;
} catch {
  await fs.writeFile(
    batchPath,
    JSON.stringify(
      {
        ...batch,
        status: 'failed',
        finished_time_bjt: bjt(),
        phase: batchPhase,
        run: currentRun || undefined,
        completed_runs: results.length,
      },
      null,
      2,
    ) + '\n',
  );
  throw new Error(`Performance batch failed at ${batchPhase}; see batch.json`);
} finally {
  if (api) await api.dispose().catch(() => undefined);
}
