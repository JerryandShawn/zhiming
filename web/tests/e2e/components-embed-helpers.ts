import { expect, type APIRequestContext, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs/promises';
import { captureComponent, componentEvidence } from './components-helpers';

export type ViewportPatch = { height?: number; offsetTop?: number; scale?: number };
type ControlledWindow = Window & { __embedViewport?: (patch: ViewportPatch) => void };
type Activity = { external: string[]; pageErrors: string[]; modelRequests: string[]; httpErrors: string[] };
const observations = new WeakMap<Page, Activity>();
const evidence = `${componentEvidence}/embed-audits`;

export async function prepareEmbed(page: Page, request: APIRequestContext) {
  const response = await request.post('/__test__/owner');
  expect(response.ok()).toBe(true);
  const owner = (await response.json()) as { token: string };
  await page.addInitScript((token) => sessionStorage.setItem('mingjing-auth-token', token), owner.token);
  const activity: Activity = { external: [], pageErrors: [], modelRequests: [], httpErrors: [] };
  observations.set(page, activity);
  page.on('request', (outgoing) => {
    const url = new URL(outgoing.url());
    if (['http:', 'https:'].includes(url.protocol) && url.origin !== 'http://127.0.0.1:4173')
      activity.external.push(url.origin);
  });
  page.on('pageerror', (error) => activity.pageErrors.push(error.message));
  page.on('response', (reply) => {
    if (reply.status() >= 400) activity.httpErrors.push(`${reply.status()} ${new URL(reply.url()).pathname}`);
  });
  // A regression must fail before it can cause any real or scripted model invocation.
  await page.route('**/api/**', async (route) => {
    const outgoing = route.request();
    const path = new URL(outgoing.url()).pathname;
    if (outgoing.method() === 'POST' && (/^\/api\/chat(?:\/|$)/.test(path) || /\/readings$/.test(path))) {
      activity.modelRequests.push(path);
      await route.abort('blockedbyclient');
    } else await route.continue();
  });
}

export async function assertEmbedSafe(page: Page, request: APIRequestContext, id: string) {
  const response = await request.get('/__test__/metrics');
  expect(response.ok()).toBe(true);
  const metrics = (await response.json()) as { real_model_calls: number; model: string; database: string };
  const activity = observations.get(page)!;
  await fs.mkdir(evidence, { recursive: true });
  await fs.writeFile(
    `${evidence}/safety-${id.replace(/[^a-zA-Z0-9-]/g, '-').slice(-48)}.json`,
    JSON.stringify(
      {
        simulation_only: true,
        real_device_verified: false,
        model: metrics.model,
        database: metrics.database,
        real_model_calls: metrics.real_model_calls,
        ...activity,
      },
      null,
      2,
    ) + '\n',
  );
  expect(metrics.real_model_calls).toBe(0);
  expect(activity).toEqual({ external: [], pageErrors: [], modelRequests: [], httpErrors: [] });
  await page.unrouteAll({ behavior: 'wait' });
}

export async function openLiveChat(page: Page) {
  await page.goto('/#/chat');
  await expect(page.getByRole('main', { name: '明镜', exact: true })).toBeVisible();
  await expect(page.getByRole('textbox', { name: '和明镜说说', exact: true })).toBeVisible();
  await expect(page.getByText('正在读取历史对话…', { exact: true })).toHaveCount(0);
  await page.evaluate(() => document.fonts.ready);
}

export async function installViewportSimulation(page: Page) {
  await page.addInitScript(() => {
    const viewport = Object.assign(new EventTarget(), {
      height: innerHeight,
      width: innerWidth,
      offsetTop: 0,
      offsetLeft: 0,
      pageTop: 0,
      pageLeft: 0,
      scale: 1,
    });
    Object.defineProperty(window, 'visualViewport', { configurable: true, value: viewport });
    Object.defineProperty(window, '__embedViewport', {
      value: (patch: { height?: number; offsetTop?: number; scale?: number }) => {
        Object.assign(viewport, patch);
        viewport.dispatchEvent(new Event('resize'));
        viewport.dispatchEvent(new Event('scroll'));
      },
    });
  });
}
export async function patchViewport(page: Page, patch: ViewportPatch) {
  await page.evaluate((value) => {
    const update = (window as ControlledWindow).__embedViewport;
    if (!update) throw new Error('VisualViewport simulation was not installed');
    update(value);
  }, patch);
}
export async function safeArea(page: Page, bottom: number, horizontal = 0) {
  const session = await page.context().newCDPSession(page);
  await session.send('Emulation.setSafeAreaInsetsOverride', {
    insets: { top: 0, left: horizontal, right: horizontal, bottom },
  });
  return session;
}
export async function auditEmbed(page: Page, name: string) {
  const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  const violations = result.violations.map((item) => ({
    id: item.id,
    impact: item.impact,
    targets: item.nodes.map((node) => node.target),
  }));
  await fs.mkdir(evidence, { recursive: true });
  await fs.writeFile(
    `${evidence}/${name}.json`,
    JSON.stringify(
      {
        name,
        simulation_only: true,
        real_device_verified: false,
        route: new URL(page.url()).hash,
        violations,
      },
      null,
      2,
    ) + '\n',
  );
  expect(violations).toEqual([]);
}
export async function captureEmbed(page: Page, name: string) {
  await captureComponent(page, `embed-${name}`);
}
