import { expect, test } from '@playwright/test';
import { createServer } from 'node:http';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import fs from 'node:fs/promises';
import path from 'node:path';

const dist = path.resolve('../static/dist');
const types: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.webmanifest': 'application/manifest+json',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.png': 'image/png',
};
const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url ?? '/', 'http://127.0.0.1');
    if (url.pathname === '/v4') {
      response.writeHead(302, { Location: '/v4/' });
      response.end();
      return;
    }
    const scoped = url.pathname.startsWith('/v4/');
    const relative = scoped
      ? url.pathname === '/v4/'
        ? 'index.html'
        : decodeURIComponent(url.pathname.slice(4))
      : url.pathname === '/'
        ? 'index.html'
        : decodeURIComponent(url.pathname);
    const filename = path.resolve(dist, relative.replace(/^\/+/, ''));
    if (!filename.startsWith(dist + path.sep)) {
      response.writeHead(404).end();
      return;
    }
    const body = await fs.readFile(filename);
    response.writeHead(200, { 'Content-Type': types[path.extname(filename)] ?? 'application/octet-stream' });
    response.end(body);
  } catch {
    response.writeHead(404).end();
  }
});
let origin = '';

test.beforeAll(async () => {
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  origin = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

test.afterAll(async () => {
  server.closeAllConnections();
  await new Promise<void>((resolve) => server.close(() => resolve()));
});

test('/v4/ serves the app, public course, manifest and scoped service worker', async ({ page }) => {
  const paths: string[] = [],
    failures: string[] = [],
    errors: string[] = [];
  page.on('request', (request) => paths.push(new URL(request.url()).pathname));
  page.on('response', (response) => {
    if (response.status() >= 400) failures.push(`${response.status()} ${new URL(response.url()).pathname}`);
  });
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${origin}/v4/?spaces=demo#/chat?space=study&topic=chart-study&view=courses`);
  await expect(page.locator('[data-course-state="ready"]')).toBeVisible();
  await expect(page.getByRole('heading', { name: '从读盘位置开始，慢慢学', exact: true })).toBeVisible();
  await expect(page.locator('.course-directory ol li')).toHaveCount(20);
  await page.evaluate(() => document.fonts.ready);
  const worker = await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready;
    return { scope: registration.scope, script: registration.active?.scriptURL };
  });
  expect(worker.scope).toBe(`${origin}/v4/`);
  expect(worker.script).toBe(`${origin}/v4/shell-sw.js`);
  expect(paths).toContain('/v4/data/study/courses-v5/course.json');
  const manifestUrl = await page
    .locator('link[rel="manifest"]')
    .evaluate((element) => (element instanceof HTMLLinkElement ? new URL(element.href).pathname : ''));
  expect(manifestUrl).toBe('/v4/pwa/manifest.webmanifest');
  const manifestResponse = await page.request.get(`${origin}${manifestUrl}`);
  expect(manifestResponse.ok()).toBe(true);
  const manifest = (await manifestResponse.json()) as { start_url: string; scope: string };
  expect(new URL(manifest.start_url, `${origin}${manifestUrl}`).pathname).toBe('/v4/');
  expect(new URL(manifest.scope, `${origin}${manifestUrl}`).pathname).toBe('/v4/');
  const shellResponse = await page.request.get(`${origin}/v4/pwa/shell-manifest.json`);
  expect(shellResponse.ok()).toBe(true);
  const shell = (await shellResponse.json()) as { assets: { path: string }[] };
  expect(shell.assets.length).toBeGreaterThan(0);
  expect(shell.assets.every((entry) => new URL(entry.path, `${origin}/v4/`).pathname.startsWith('/v4/'))).toBe(true);
  expect(paths).toContain('/v4/fonts/fonts.css');
  expect(paths.every((item) => item.startsWith('/v4/'))).toBe(true);
  expect(failures).toEqual([]);
  expect(errors).toEqual([]);
  const directory = path.resolve('evidence/2026-10-30/v4-base');
  await fs.mkdir(directory, { recursive: true });
  await page.screenshot({
    path: path.join(directory, 'courses-light-390.png'),
    fullPage: true,
    animations: 'disabled',
  });
});

test('/v4 redirects to the scoped app and the old root build remains usable', async ({ page, request }) => {
  const redirected = await request.get(`${origin}/v4`, { maxRedirects: 0 });
  expect(redirected.status()).toBe(302);
  expect(redirected.headers().location).toBe('/v4/');
  await page.goto(`${origin}/v4/?spaces=demo#/spaces?space=career`);
  await expect(page.getByRole('heading', { name: '事业的话题', exact: true })).toBeVisible();
  await page.goto(`${origin}/?spaces=demo#/spaces?space=career`);
  await expect(page.getByRole('heading', { name: '事业的话题', exact: true })).toBeVisible();
});
