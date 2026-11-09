import { expect, test, type BrowserContext, type Page, type TestInfo } from '@playwright/test';
import fs from 'node:fs/promises';
import { deflateSync } from 'node:zlib';
import { auditNight } from './night-helpers';

test.use({ timezoneId: 'Asia/Shanghai', serviceWorkers: 'allow' });
const origin = 'http://127.0.0.1:4173';
type Manifest = { version: string; assets: { path: string; bytes: number; sha256: string }[] };
type Activity = {
  blocked: string[];
  external: string[];
  errors: string[];
  console: { text: string; url: string }[];
  fonts: { url: string; error: string }[];
};
const activity = new WeakMap<Page, Activity>();
function markedPng(marker: string) {
  const chunk = (name: string, data: Buffer) => {
    const body = Buffer.concat([Buffer.from(name), data]);
    let checksum = 0xffffffff;
    for (const byte of body) {
      checksum ^= byte;
      for (let bit = 0; bit < 8; bit++) checksum = (checksum >>> 1) ^ (checksum & 1 ? 0xedb88320 : 0);
    }
    const length = Buffer.alloc(4),
      crc = Buffer.alloc(4);
    length.writeUInt32BE(data.length);
    crc.writeUInt32BE((checksum ^ 0xffffffff) >>> 0);
    return Buffer.concat([length, body, crc]);
  };
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk('IHDR', Buffer.from([0, 0, 0, 1, 0, 0, 0, 1, 8, 6, 0, 0, 0])),
    chunk('IDAT', deflateSync(Buffer.from([0, 180, 45, 90, 255]))),
    chunk('tEXt', Buffer.from(`Note\0${marker}`)),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}
const fontUrl = (url: string) => {
  const parsed = new URL(url);
  return parsed.origin === origin && /^\/fonts\/noto-(?:sans|serif)-sc-[\w-]+\.woff2$/.test(parsed.pathname);
};
test.beforeEach(async ({ page, context }) => {
  const record: Activity = { blocked: [], external: [], errors: [], console: [], fonts: [] };
  activity.set(page, record);
  context.on('request', (request) => {
    const url = new URL(request.url());
    if (url.origin === origin && /^\/(?:api|static|__test__)(?:\/|$)/.test(url.pathname)) record.blocked.push(url.href);
    if (['http:', 'https:'].includes(url.protocol) && url.origin !== origin) record.external.push(url.href);
  });
  await context.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (
      ['http:', 'https:'].includes(url.protocol) &&
      (url.origin !== origin || /^\/(?:api|static|__test__)(?:\/|$)/.test(url.pathname))
    )
      await route.abort('blockedbyclient');
    else await route.continue();
  });
  page.on('pageerror', (error) => record.errors.push(error.message));
  page.on('console', (message) => record.console.push({ text: message.text(), url: message.location().url }));
  page.on('requestfailed', (request) => {
    const error = request.failure()?.errorText ?? '';
    if (fontUrl(request.url()) && error === 'net::ERR_INTERNET_DISCONNECTED')
      record.fonts.push({ url: request.url(), error });
    else record.errors.push(`Unexpected request failure: ${request.url()} ${error}`);
  });
});
test.afterEach(async ({ page, context }, info) => {
  await context.setOffline(false);
  const record = activity.get(page)!;
  const allowed = new Set(record.fonts.map((item) => item.url));
  const unexpected = record.console.filter(
    (item) =>
      !(
        allowed.has(item.url) &&
        fontUrl(item.url) &&
        /^Failed to load resource: net::ERR_INTERNET_DISCONNECTED$/.test(item.text)
      ),
  );
  info.annotations.push({ type: 'offline_font_failures', description: JSON.stringify(record.fonts) });
  expect(record.blocked).toEqual([]);
  expect(record.external).toEqual([]);
  expect(record.errors).toEqual([]);
  expect(record.fonts).toEqual([]);
  expect(unexpected).toEqual([]);
});

async function bootstrap(page: Page, width = 1440, theme = 'light', route = 'today') {
  await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
  await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
  await page.goto(`/?night=demo#/${route}`);
  await expect(page.getByRole('complementary', { name: '本地演示说明' })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });
  // Fresh contexts demonstrate that installation does not claim the page or reload it.
  expect(await page.evaluate(() => navigator.serviceWorker.controller)).toBeNull();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true);
  await expect(page.getByRole('complementary', { name: '本地演示说明' })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  const manifest = (await page.evaluate(async () => {
    const response = await fetch('/pwa/shell-manifest.json', { credentials: 'omit', cache: 'no-store' });
    if (!response.ok) throw new Error('Missing built shell manifest');
    return await response.json();
  })) as Manifest;
  return manifest;
}
async function assertCache(page: Page, manifest: Manifest, markers: string[] = []) {
  const result = await page.evaluate(
    async ({ manifest, markers }) => {
      const registration = await navigator.serviceWorker.ready;
      const prefix = `mingjing-shell-v1:${encodeURIComponent(new URL(registration.scope).pathname)}:`;
      const names = await caches.keys(),
        rows = [];
      for (const name of names) {
        const cache = await caches.open(name);
        for (const request of await cache.keys()) {
          const response = await cache.match(request),
            bytes = await response!.arrayBuffer();
          const text = new TextDecoder().decode(bytes);
          const sha256 = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
            .map((value) => value.toString(16).padStart(2, '0'))
            .join('');
          rows.push({
            cache: name,
            url: request.url,
            bytes: bytes.byteLength,
            sha256,
            leaked: markers.filter((marker) => text.includes(marker) || request.url.includes(marker)),
          });
        }
      }
      return {
        names,
        expectedName: prefix + manifest.version,
        rows,
        expectedUrls: manifest.assets.map((item) => new URL(item.path, registration.scope).href).sort(),
      };
    },
    { manifest, markers },
  );
  expect(result.names).toEqual([result.expectedName]);
  expect(result.rows.map((row) => row.url).sort()).toEqual(result.expectedUrls);
  for (const asset of manifest.assets) {
    const row = result.rows.find((item) => new URL(item.url).pathname === `/${asset.path}`)!;
    expect(row).toMatchObject({ cache: result.expectedName, bytes: asset.bytes, sha256: asset.sha256, leaked: [] });
  }
  expect(result.rows.every((row) => row.leaked.length === 0)).toBe(true);
}
async function capture(page: Page, name: string) {
  const directory = process.env.NIGHT_EVIDENCE_DIR || 'evidence/2026-10-21';
  await fs.mkdir(directory, { recursive: true });
  await page.screenshot({ path: `${directory}/${name}.png`, animations: 'disabled' });
}
async function offline(page: Page, context: BrowserContext, manifest: Manifest, info: TestInfo) {
  await context.setOffline(true);
  await expect(page.getByRole('status').filter({ hasText: '离线中' })).toBeVisible();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('complementary', { name: '本地演示说明' })).toBeVisible();
  await expect(page.getByRole('status').filter({ hasText: '离线中' })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await assertCache(page, manifest);
  await auditNight(page);
  info.annotations.push({ type: 'cache_scope', description: 'Built allowlist bytes only; no runtime cache writes.' });
}

for (const theme of ['light', 'dark'])
  for (const width of [390, 1440]) {
    test(`真实SW离线空壳与静态缓存白名单 ${width} ${theme}`, async ({ page, context }, info) => {
      const manifest = await bootstrap(page, width, theme);
      await assertCache(page, manifest);
      await offline(page, context, manifest, info);
      await capture(page, `Q5-pwa-offline-${width}-${theme}`);
      await context.setOffline(false);
      await expect(page.getByRole('status').filter({ hasText: '离线中' })).toHaveCount(0);
    });
  }

test('未知资源、凭据、SSE、POST和上传均network-only且不写缓存', async ({ page }) => {
  const manifest = await bootstrap(page);
  const marker = `SYNTHETIC_PWA_NETWORK_${crypto.randomUUID()}`;
  const asset = '/' + manifest.assets.find((item) => item.path.endsWith('.js'))!.path;
  const seen: { path: string; method: string; body: string | null }[] = [];
  await page.route('**/*', async (route) => {
    const request = route.request(),
      url = new URL(request.url()),
      headers = request.headers();
    if (
      url.origin === origin &&
      (url.pathname.startsWith('/__pwa_test__/') ||
        (url.pathname === asset &&
          (headers.authorization ||
            headers['x-token'] ||
            headers['x-api-key'] ||
            headers.accept?.includes('text/event-stream'))))
    ) {
      seen.push({ path: url.pathname, method: request.method(), body: request.postData() });
      await route.fulfill({
        status: 200,
        contentType: url.pathname.endsWith('/navigation') ? 'text/html' : 'text/plain',
        body: url.pathname.endsWith('/navigation')
          ? `<html lang="zh-CN"><title>本地模拟</title><body>${marker}</body></html>`
          : marker,
      });
    } else await route.fallback();
  });
  const results = await page.evaluate(
    async ({ asset, marker }) => {
      const requests: [string, RequestInit][] = [
        ['/__pwa_test__/unknown.json', {}],
        [asset, { headers: { Authorization: `Bearer ${marker}` } }],
        [asset, { headers: { 'X-Token': marker } }],
        [asset, { headers: { 'X-Api-Key': marker } }],
        [asset, { headers: { Accept: 'text/event-stream' } }],
        ['/__pwa_test__/chat', { method: 'POST', body: marker }],
        ['/__pwa_test__/uploads/image.png', { method: 'POST', body: new Blob([marker], { type: 'image/png' }) }],
      ];
      return await Promise.all(
        requests.map(async ([url, init]) => await (await fetch(url, { ...init, cache: 'no-store' })).text()),
      );
    },
    { asset, marker },
  );
  expect(results).toEqual(Array(7).fill(marker));
  expect(seen).toHaveLength(7);
  expect(seen.filter((item) => item.method === 'POST').every((item) => item.body?.includes(marker))).toBe(true);
  await page.goto('/__pwa_test__/navigation');
  await expect(page.locator('body')).toHaveText(marker);
  await assertCache(page, manifest, [marker]);
  await page.goto('/?night=demo#/today');
  await expect(page.getByRole('complementary', { name: '本地演示说明' })).toBeVisible();
  await assertCache(page, manifest, [marker]);
  await auditNight(page);
  await capture(page, 'Q5-pwa-network-only-1440-light');
});

test('普通排队与无痕正文附图退出刷新后均不进入CacheStorage', async ({ page }) => {
  const manifest = await bootstrap(page, 390, 'dark', 'chat');
  const suffix = crypto.randomUUID(),
    queueMarker = `SYNTHETIC_PWA_QUEUE_${suffix}`,
    privateMarker = `SYNTHETIC_PWA_PRIVATE_${suffix}`,
    imageMarker = `SYNTHETIC_PWA_IMAGE_${suffix}`;
  const input = page.getByRole('textbox', { name: '和明镜说说', exact: true });
  await expect(page.locator('[data-page="chat"][data-scenario]')).toHaveAttribute('data-complete', 'true');
  await page.getByRole('button', { name: '查看插话排队', exact: true }).click();
  await input.fill(queueMarker);
  await page.getByRole('button', { name: '排队发送', exact: true }).click();
  await expect(page.getByRole('region', { name: '排队消息' }).getByRole('listitem')).toHaveAttribute(
    'data-queue-state',
    'queued',
  );
  await page.getByRole('switch', { name: '无痕模式', exact: true }).click();
  const privateRoot = page.locator('[data-privacy="incognito"]');
  await expect(privateRoot).toBeVisible();
  await expect(page.getByRole('region', { name: '排队消息' })).toHaveCount(0);
  const png = markedPng(imageMarker);
  await page
    .getByLabel('选择本轮图片', { exact: true })
    .setInputFiles({ name: 'synthetic-private.png', mimeType: 'image/png', buffer: png });
  await input.fill(privateMarker);
  await expect(page.getByRole('button', { name: '发送', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(privateRoot.getByText(privateMarker, { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '退出无痕', exact: true }).click();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('complementary', { name: '本地演示说明' })).toBeVisible();
  await expect(input).toHaveValue('');
  await expect(page.getByRole('region', { name: '排队消息' })).toHaveCount(0);
  await expect(page.locator('.composer img')).toHaveCount(0);
  const markers = [queueMarker, privateMarker, imageMarker, png.toString('base64')];
  for (const marker of markers) await expect(page.locator('body')).not.toContainText(marker);
  expect(
    await page.evaluate(() => [localStorage, sessionStorage].flatMap((storage) => Object.values(storage))),
  ).not.toEqual(expect.arrayContaining(markers));
  const stored = await page.evaluate(() =>
    [localStorage, sessionStorage].flatMap((storage) => Object.values(storage)).join('\n'),
  );
  for (const marker of markers) expect(stored).not.toContain(marker);
  await assertCache(page, manifest, markers);
  await auditNight(page);
  await capture(page, 'Q5-pwa-private-cleared-390-dark');
});
