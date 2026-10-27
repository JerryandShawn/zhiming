import fs from 'node:fs/promises';
import path from 'node:path';
import type { Page } from '@playwright/test';

const root = path.resolve('..');
const origin = 'https://legacy.fixture.invalid';
const runId = 'synthetic-legacy-browser';
const firstText = '先看已经确认的部分。';
const finalText = '修订后，先核对日期，再决定下一步。';
function frame(seq: number, type: string, body: Record<string, unknown>) {
  return `id: ${seq}\nevent: ${type}\ndata: ${JSON.stringify({
    v: 1,
    run_id: runId,
    seq,
    ts: '2026-10-27T09:20:00+08:00',
    ...body,
  })}\n\n`;
}
const final = () =>
  frame(5, 'final', {
    message_id: 'synthetic-message',
    envelope: {
      schema: 'core4.0',
      message_id: 'synthetic-message',
      text: finalText,
      receipts: [],
      used_fact_ids: [],
      used_claim_ids: [],
      asked: null,
      options: null,
      review: { state: 'revised', reasons: [], revision_id: 'synthetic-revision' },
      usage: {},
    },
  });
export async function prepareLegacy(
  page: Page,
  scenario: 'revised' | 'cancelled' | 'legacy' | 'bad-receipt' = 'revised',
) {
  const outside: string[] = [],
    errors: string[] = [],
    cursors: (string | null)[] = [];
  const writes: string[] = [];
  let cancelled = false,
    connections = 0;
  let release!: () => void;
  const gate = new Promise<void>((resolve) => (release = resolve));
  page.on('close', release);
  page.on('pageerror', (error) => errors.push(error.message));
  await page.addInitScript(() => {
    localStorage.setItem('mjt_token', 'synthetic-browser-token');
  });
  await page.route('**/*', async (route) => {
    const request = route.request(),
      url = new URL(request.url());
    if (url.origin !== origin) {
      outside.push(url.origin);
      await route.abort();
      return;
    }
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.pathname.startsWith('/api/')) {
      if (request.method() !== 'GET') writes.push(`${request.method()} ${url.pathname}`);
      if (url.pathname === '/api/chat' && request.method() === 'POST') {
        if (scenario === 'legacy')
          return route.fulfill({
            contentType: 'text/event-stream',
            body:
              'data: ' +
              JSON.stringify({ type: 'started', run_id: runId }) +
              '\n\ndata: ' +
              JSON.stringify({ type: 'result', result: { answer: '旧格式完整回答' } }) +
              '\n\ndata: [DONE]\n\n',
          });
        return json(
          {
            run_id: runId,
            message_id: 'synthetic-message',
            thread_id: 'life:self',
            status: 'queued',
            runtime: 'v4',
            run_url: `/api/runs/${runId}`,
            events_url: scenario === 'bad-receipt' ? 'https://foreign.invalid/events' : `/api/runs/${runId}/events`,
          },
          202,
        );
      }
      if (url.pathname === `/api/runs/${runId}/cancel` && request.method() === 'POST') {
        cancelled = true;
        release();
        return json({ ok: true });
      }
      if (url.pathname === `/api/runs/${runId}/events`) {
        cursors.push(request.headers()['last-event-id'] ?? null);
        if (++connections === 1)
          return route.fulfill({
            contentType: 'text/event-stream',
            body: frame(1, 'text_delta', { text: firstText }) + frame(2, 'review', { state: 'pending', reasons: [] }),
          });
        await gate;
        if (page.isClosed()) {
          await route.abort().catch(() => undefined);
          return;
        }
        return route.fulfill({
          contentType: 'text/event-stream',
          body: cancelled
            ? frame(3, 'error', { code: 'RUN_CANCELLED', message: '已停止', retryable: false })
            : frame(2, 'review', { state: 'pending', reasons: [] }) +
              frame(3, 'text_reset', { text: finalText, reason: 'revised', revision_id: 'synthetic-revision' }) +
              frame(4, 'review', { state: 'revised', reasons: [], revision_id: 'synthetic-revision' }) +
              final(),
        });
      }
      if (request.method() !== 'GET') return json({ detail: 'unexpected fixture write' }, 400);
      if (url.pathname === '/api/sessions') return json([{ id: 'shared', title: '合成浏览器对话' }]);
      if (url.pathname === '/api/health') return json({ ok: true });
      if (url.pathname === '/api/state') return json({ revision: 1, facts: [], cases: [], settings: {} });
      if (url.pathname === '/api/history' || url.pathname === '/api/cases' || url.pathname === '/api/memories')
        return json([]);
      return json({});
    }
    if (url.pathname === '/favicon.ico') return route.fulfill({ status: 204 });
    const file =
      url.pathname === '/'
        ? path.join(root, 'static/index.html')
        : path.resolve(root, '.' + decodeURIComponent(url.pathname));
    if (!file.startsWith(path.join(root, 'static') + path.sep)) {
      await route.abort();
      return;
    }
    try {
      const contentType =
        (
          {
            '.html': 'text/html',
            '.js': 'text/javascript',
            '.css': 'text/css',
            '.svg': 'image/svg+xml',
            '.woff2': 'font/woff2',
            '.png': 'image/png',
          } as Record<string, string>
        )[path.extname(file)] ?? 'application/octet-stream';
      await route.fulfill({ contentType, body: await fs.readFile(file) });
    } catch {
      await route.fulfill({ status: 404, body: 'fixture asset unavailable' });
    }
  });
  await page.goto(origin + '/#/chat');
  await page.waitForFunction(() => Boolean(window.mingjingLegacyStream));
  return { outside, errors, cursors, writes, release, firstText, finalText };
}
