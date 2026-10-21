import { expect, test, type Route } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { auditNight } from './night-helpers';
for (const width of [390, 1440])
  test(`历史GET重读期间可继续编辑草稿且不重发 ${width}`, async ({ page }, info) => {
    const calls: { path: string; method: string }[] = [],
      errors: string[] = [];
    let retry = false,
      pending: Route | undefined,
      release!: () => void;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.setViewportSize({ width, height: 900 });
    await page.clock.setFixedTime(new Date('2026-10-21T08:00:00+08:00'));
    await page.addInitScript(
      (theme) => {
        sessionStorage.setItem('mingjing-auth-token', 'synthetic-history-browser');
        localStorage.setItem('mingjing-theme', theme);
      },
      width === 390 ? 'dark' : 'light',
    );
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('console', (m) => errors.push(m.text()));
    await page.route('**/*', async (route) => {
      const request = route.request(),
        url = new URL(request.url());
      if (['http:', 'https:'].includes(url.protocol) && url.origin !== 'http://127.0.0.1:4173')
        throw new Error('Unexpected external request');
      if (!url.pathname.startsWith('/api/')) return route.continue();
      calls.push({ path: url.pathname, method: request.method() });
      if (request.method() !== 'GET' || url.pathname !== '/api/history')
        return route.fulfill({ status: 409, body: '{}' });
      if (!retry) return route.fulfill({ status: 200, contentType: 'application/json', body: '{' });
      pending = route;
      await held;
    });
    try {
      await page.goto('/#/chat');
      const button = page.getByRole('button', { name: '重新读取历史对话', exact: true }),
        input = page.getByRole('textbox', { name: '和明镜说说', exact: true });
      await expect(button).toBeVisible();
      await input.fill('重读之前的合成普通草稿');
      const baseline = calls.length;
      retry = true;
      await button.click();
      await expect.poll(() => Boolean(pending)).toBe(true);
      await expect(button).toBeDisabled();
      await expect(button).toHaveAttribute('aria-busy', 'true');
      await input.fill('等待重读时继续编辑的合成普通草稿');
      expect(calls.length).toBe(baseline + 1);
      const folder = process.env.NIGHT_EVIDENCE_DIR ?? 'evidence/2026-10-21/history-retry';
      await fs.mkdir(folder, { recursive: true });
      const capture = async (name: string) => {
        await page.evaluate(() => window.scrollTo(0, 0));
        const file = path.join(folder, `${name}-${width}.png`);
        await fs.writeFile(file, await page.screenshot({ fullPage: true, animations: 'disabled' }), { flag: 'wx' });
        info.annotations.push({ type: 'history_screenshot', description: file.replaceAll('\\', '/') });
      };
      await auditNight(page);
      await capture('history-retrying-draft');
      await pending!.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            role: 'assistant',
            content: '重新读到的合成历史回答',
            at: '2026-10-21T00:00:00+08:00',
            source: 'web',
            cursor: 'synthetic-row',
            turn_id: 'synthetic-turn',
          },
        ]),
      });
      release();
      pending = undefined;
      await expect(page.getByText('重新读到的合成历史回答', { exact: true })).toBeVisible();
      await expect(button).toHaveCount(0);
      await expect(input).toHaveValue('等待重读时继续编辑的合成普通草稿');
      expect(calls.every((call) => call.method === 'GET' && call.path === '/api/history')).toBe(true);
      expect(errors).toEqual([]);
      await auditNight(page);
      await capture('history-recovered-draft');
    } finally {
      if (pending) {
        await pending.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
        release();
      }
    }
  });
