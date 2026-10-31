import { expect, test, type Route } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { auditNight } from './night-helpers';

const card = {
  card_id: 'major-17',
  name: '星星',
  upright: '先核对现实',
  reversed: '放慢节奏',
  misreading: '不是保证',
  question: '下一步怎么做',
};
const draw = (id: string) => ({
  id,
  question: `合成牌阵${id.toUpperCase()}`,
  case_id: 'synthetic',
  draw_source: 'auto',
  status: 'ready',
  reversals: true,
  spread_id: 'focus1',
  spread: { id: 'focus1', name: '关注点', positions: ['现在'] },
  created_at: '2026-10-21T00:00:00Z',
  revision: 1,
  cards: [{ position: 1, label: '现在', back_id: 'opaque', revealed: true, card, orientation: 'upright' }],
  backs: [],
  options: {},
});
const reading = (id: string, version = 1) => [
  {
    id: `reading-${id}-${version}`,
    version,
    status: 'success',
    result: { answer: `牌阵${id.toUpperCase()}已保存的第${version}版`, professional_appendix: '合成静态说明' },
  },
];

for (const width of [390, 1440])
  test(`塔罗手动刷新：切盘迟到不串版，失败后GET重试 ${width}`, async ({ page }, info) => {
    const calls: { path: string; method: string }[] = [],
      errors: string[] = [],
      external: string[] = [];
    let pending: Route | undefined, release!: () => void;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    const counts = { a: 0, b: 0 };
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(
      (theme) => {
        sessionStorage.setItem('mingjing-auth-token', 'synthetic-ui-refresh');
        localStorage.setItem('mingjing-theme', theme);
      },
      width === 390 ? 'dark' : 'light',
    );
    await page.clock.setFixedTime(new Date('2026-10-21T08:00:00+08:00'));
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('console', (message) => errors.push(`${message.type()}: ${message.text()}`));
    await page.route('**/*', async (route) => {
      const request = route.request(),
        url = new URL(request.url());
      if (['http:', 'https:'].includes(url.protocol) && url.origin !== 'http://127.0.0.1:4173') {
        external.push(url.origin);
        await route.abort();
        return;
      }
      if (['/static/tarot/major-17.svg', '/static/tarot/back.svg'].includes(url.pathname))
        return route.fulfill({
          status: 200,
          contentType: 'image/svg+xml',
          body: await fs.readFile(path.resolve('../static/tarot', path.basename(url.pathname))),
        });
      if (url.pathname.startsWith('/static/')) throw new Error('Unexpected synthetic static resource');
      if (!url.pathname.startsWith('/api/')) return route.continue();
      calls.push({ path: url.pathname, method: request.method() });
      const json = (value: unknown) =>
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(value) });
      if (request.method() !== 'GET') return route.fulfill({ status: 409, body: '{}' });
      if (url.pathname === '/api/tarot/deck') return json({ cards: [card], spreads: [draw('a').spread] });
      if (url.pathname === '/api/tarot/draws') return json([draw('a'), draw('b')]);
      if (url.pathname === '/api/cases') return json([]);
      const match = url.pathname.match(/^\/api\/tarot\/draws\/([ab])(\/readings)?$/);
      if (!match) throw new Error('Unexpected synthetic GET');
      const id = match[1] as 'a' | 'b';
      if (!match[2]) return json(draw(id));
      counts[id]++;
      if (id === 'a' && counts.a === 2) {
        pending = route;
        await held;
        return;
      }
      if (id === 'b' && counts.b === 2)
        return route.fulfill({ status: 200, contentType: 'application/json', body: '{' });
      return json(reading(id, id === 'b' && counts.b === 3 ? 2 : 1));
    });
    try {
      await page.goto('/#/tarot?draw=a');
      await expect(page.getByText('牌阵A已保存的第1版', { exact: true })).toBeVisible();
      const refresh = page.getByRole('button', { name: '刷新解读记录', exact: true });
      await refresh.click();
      await expect.poll(() => Boolean(pending)).toBe(true);
      await page
        .locator('.tarot-history')
        .getByRole('button', { name: /合成牌阵B/ })
        .click();
      await expect(page.getByText('牌阵B已保存的第1版', { exact: true })).toBeVisible();
      await pending!.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(reading('a', 2)) });
      release();
      pending = undefined;
      await expect(page.getByText('牌阵A已保存的第2版', { exact: true })).toHaveCount(0);
      await expect(page.getByText('牌阵B已保存的第1版', { exact: true })).toBeVisible();
      await refresh.click();
      await expect(page.getByText('解读记录暂时无法读取。', { exact: true })).toBeVisible();
      await expect(page.getByText('牌阵B已保存的第1版', { exact: true })).toBeVisible();
      const root = process.env.NIGHT_EVIDENCE_DIR ?? 'test-results/tarot-refresh';
      await fs.mkdir(root, { recursive: true });
      const folder = process.env.NIGHT_EVIDENCE_DIR ? root : await fs.mkdtemp(path.join(root, 'run-'));
      const capture = async (name: string) => {
        await page.evaluate(() => window.scrollTo(0, 0));
        const file = path.join(folder, `${name}-${width}.png`);
        await fs.writeFile(file, await page.screenshot({ fullPage: true, animations: 'disabled' }), { flag: 'wx' });
        info.annotations.push({ type: 'refresh_screenshot', description: file.replaceAll('\\', '/') });
      };
      await auditNight(page);
      await capture('refresh-failed-preserved');
      await refresh.click();
      await expect(page.getByText('牌阵B已保存的第2版', { exact: true })).toBeVisible();
      await expect(page.getByText('解读记录已刷新。', { exact: true })).toBeVisible();
      await expect(page.getByText('解读记录暂时无法读取。', { exact: true })).toHaveCount(0);
      await expect(page.getByRole('heading', { name: '合成牌阵B', exact: true })).toBeVisible();
      await auditNight(page);
      await capture('refresh-retried-current');
      expect(calls.every((call) => call.method === 'GET')).toBe(true);
      expect(calls.filter((call) => call.path === '/api/tarot/draws/b/readings')).toHaveLength(3);
      expect(errors).toEqual([]);
      expect(external).toEqual([]);
    } finally {
      if (pending) {
        await pending.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
        release();
      }
    }
  });
