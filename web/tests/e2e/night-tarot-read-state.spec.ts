import { expect, test, type Route } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { auditNight } from './night-helpers';

const card = {
  card_id: 'major-17',
  name: '星星',
  upright: '先核对现实条件',
  reversed: '放慢节奏',
  misreading: '不是保证',
  question: '下一步怎么做？',
};
const fixed = {
  id: 'read-state-fixed',
  question: '合成固定牌阵的读取状态',
  case_id: 'synthetic',
  draw_source: 'auto',
  status: 'ready',
  reversals: true,
  spread_id: 'focus1',
  spread: { id: 'focus1', name: '关注点', positions: ['现在'] },
  created_at: '2026-10-21T00:00:00Z',
  revision: 1,
  backs: [],
  options: {},
  cards: [{ position: 1, label: '现在', back_id: 'opaque', revealed: true, card, orientation: 'upright' }],
};
const reading = [
  { id: 'read-state-version', version: 1, status: 'success', result: { answer: '已保存的合成解读：先核对现实安排。' } },
];

for (const width of [390, 1440])
  test(`固定塔罗初读：loading/error不生成，GET重读保留背景 ${width}`, async ({ page }, info) => {
    const calls: { path: string; method: string }[] = [],
      errors: string[] = [],
      external: string[] = [];
    let pending: Route | undefined,
      release!: () => void,
      reads = 0;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(
      (theme) => {
        sessionStorage.setItem('mingjing-auth-token', 'synthetic-ui-read-state');
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
        return route.abort();
      }
      if (!url.pathname.startsWith('/api/')) return route.continue();
      calls.push({ path: url.pathname, method: request.method() });
      const json = (value: unknown) =>
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(value) });
      if (request.method() !== 'GET') return route.fulfill({ status: 409, body: '{}' });
      if (url.pathname === '/api/tarot/deck') return json({ cards: [card], spreads: [fixed.spread], reversals: true });
      if (url.pathname === '/api/tarot/draws') return json([fixed]);
      if (url.pathname === '/api/cases') return json([]);
      if (url.pathname === `/api/tarot/draws/${fixed.id}`) return json(fixed);
      if (url.pathname === `/api/tarot/draws/${fixed.id}/readings`) {
        if (++reads === 1) {
          pending = route;
          await held;
          return;
        }
        return json(reading);
      }
      throw new Error('Unexpected synthetic read-state route');
    });
    const folder = process.env.NIGHT_EVIDENCE_DIR ?? 'evidence/2026-10-21/tarot-read-state';
    await fs.mkdir(folder, { recursive: true });
    const capture = async (state: string) => {
      await page.evaluate(() => window.scrollTo(0, 0));
      const file = path.join(folder, `${state}-${width}.png`);
      await fs.writeFile(file, await page.screenshot({ fullPage: true, animations: 'disabled' }), { flag: 'wx' });
      info.annotations.push({ type: 'read_state_screenshot', description: file.replaceAll('\\', '/') });
    };
    try {
      await page.goto(`/#/tarot?draw=${fixed.id}`);
      await expect(page.getByRole('heading', { name: fixed.question, exact: true })).toBeVisible();
      await expect.poll(() => Boolean(pending)).toBe(true);
      await page.evaluate(() => document.fonts.ready);
      const panel = page.getByRole('region', { name: '固定牌阵解读' });
      const generate = panel.getByRole('button', { name: '生成 AI 解读', exact: true });
      const supplement = panel.getByRole('textbox', { name: '补充现实背景' });
      await expect(panel.getByText('正在读取已保存的解读版本…', { exact: true })).toBeVisible();
      await expect(generate).toBeDisabled();
      await expect(page.getByRole('img', { name: '星星 · 正位', exact: true })).toBeVisible();
      await supplement.fill('合成背景：先保留这段补充，再核对已有版本。');
      await auditNight(page);
      await capture('initial-loading');
      // A valid JSON object is still an invalid list receipt; do not coerce it into [].
      await pending!.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
      release();
      pending = undefined;
      await expect(
        panel.getByText('解读版本暂时无法读取。先刷新记录，再决定是否开始新解读。', { exact: true }),
      ).toBeVisible();
      await expect(generate).toBeDisabled();
      await expect(supplement).toHaveValue('合成背景：先保留这段补充，再核对已有版本。');
      await expect(page.getByRole('img', { name: '星星 · 正位', exact: true })).toBeVisible();
      expect(reads).toBe(1);
      await auditNight(page);
      await capture('initial-error');
      await panel.getByRole('button', { name: '刷新解读记录', exact: true }).click();
      await expect(panel.getByText(reading[0].result.answer, { exact: true })).toBeVisible();
      await expect(panel.getByRole('button', { name: '重新解读 · 不换牌', exact: true })).toBeEnabled();
      await expect(panel.getByText('正在读取已保存的解读版本…', { exact: true })).toHaveCount(0);
      await expect(
        panel.getByText('解读版本暂时无法读取。先刷新记录，再决定是否开始新解读。', { exact: true }),
      ).toHaveCount(0);
      await expect(supplement).toHaveValue('合成背景：先保留这段补充，再核对已有版本。');
      await expect(page.getByRole('img', { name: '星星 · 正位', exact: true })).toBeVisible();
      await auditNight(page);
      await capture('read-retry-ready');
      expect(reads).toBe(2);
      expect(calls.every((call) => call.method === 'GET')).toBe(true);
      expect(calls.filter((call) => call.path.endsWith('/readings'))).toHaveLength(2);
      expect(errors).toEqual([]);
      expect(external).toEqual([]);
    } finally {
      if (pending) {
        await pending.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
        release();
      }
    }
  });
