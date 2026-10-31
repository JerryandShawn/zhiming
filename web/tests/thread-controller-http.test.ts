// @vitest-environment node
// Real loopback HTTP needs Node fetch with its own AbortSignal; jsdom signals are rejected on Node 24.
import { createServer, type ServerResponse } from 'node:http';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import { describe, expect, it, vi } from 'vitest';
import { createThreadController } from '../src/threads/controller';
import type { ThreadAcceptance } from '../src/threads/contracts';

describe('controller over synthetic real loopback HTTP', () => {
  it.each(['complete', 'cancel'] as const)(
    '%s uses durable authority and never resends a message',
    async (scenario) => {
      const receipt: ThreadAcceptance = {
        run_id: 'synthetic-controller-http',
        thread_id: 'life:self',
        status: 'queued',
        runtime: 'v4',
        run_url: '/api/runs/synthetic-controller-http',
        events_url: '/api/runs/synthetic-controller-http/events',
      };
      const envelope = {
        schema: 'core4.0',
        message_id: 'synthetic-message',
        text: '本机合成修订终稿',
        receipts: [],
        used_fact_ids: [],
        used_claim_ids: [],
        asked: null,
        options: null,
        review: { state: 'revised', revision_id: 'synthetic-r1', reasons: [] },
        usage: {},
      };
      const frame = (seq: number, type: string, body: Record<string, unknown>) =>
        `id: ${seq}\nevent: ${type}\ndata: ${JSON.stringify({ v: 1, run_id: receipt.run_id, seq, ts: '2026-10-27T18:00:00+08:00', ...body })}\n\n`;
      let persisted = 'running';
      let events: ServerResponse | undefined;
      const requests: { method?: string; path?: string; token?: string }[] = [];
      const server = createServer((req, res) => {
        requests.push({ method: req.method, path: req.url, token: req.headers['x-token'] as string | undefined });
        req.resume();
        if (req.method === 'GET' && req.url === receipt.events_url) {
          events = res;
          res.writeHead(200, { 'Content-Type': 'text/event-stream' });
          res.write(frame(1, 'text_delta', { text: '合成部分正文' }));
          if (scenario === 'complete')
            setImmediate(() => {
              persisted = 'succeeded';
              res.end(
                frame(2, 'review', { state: 'pending', reasons: [] }) +
                  frame(3, 'text_reset', { text: envelope.text, reason: 'revised', revision_id: 'synthetic-r1' }) +
                  frame(4, 'review', envelope.review) +
                  frame(5, 'final', { message_id: envelope.message_id, envelope }),
              );
            });
        } else if (req.method === 'GET' && req.url === receipt.run_url) {
          res.setHeader('Content-Type', 'application/json');
          res.end(
            JSON.stringify({
              id: receipt.run_id,
              operation_id: 'synthetic-operation',
              status: persisted,
              calls: 1,
              call_limit: 12,
              attempts: 1,
              checkpoint: {},
              dependencies: [],
              error: 'PRIVATE_SENTINEL',
              result: persisted === 'succeeded' ? { ...envelope, answer: envelope.text } : {},
            }),
          );
        } else if (req.method === 'POST' && req.url === `${receipt.run_url}/cancel`) {
          res.setHeader('Content-Type', 'application/json');
          res.end(JSON.stringify({ ok: true, run_id: receipt.run_id }));
        } else {
          res.writeHead(404);
          res.end();
        }
      });
      server.listen(0, '127.0.0.1');
      await once(server, 'listening');
      const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
      const fetcher: typeof fetch = (path, init) => fetch(new URL(String(path), base), init);
      const controller = createThreadController(receipt, {
        fetcher,
        signal: new AbortController().signal,
        isCurrent: () => true,
        headers: () => ({ 'X-Token': 'synthetic-only' }),
        maxReconnects: 0,
      });
      try {
        const task = controller.start();
        if (scenario === 'cancel') {
          await vi.waitFor(() => expect(controller.getSnapshot().stream.text).toBe('合成部分正文'));
          const began = performance.now(),
            stopping = controller.stop();
          await vi.waitFor(() => expect(controller.getSnapshot().stopping).toBe(true));
          expect(performance.now() - began).toBeLessThan(2000);
          await stopping;
          expect(controller.getSnapshot()).toMatchObject({ phase: 'following', stopping: true });
          persisted = 'cancelled';
          events!.end(frame(3, 'error', { code: 'RUN_CANCELLED', message: '本轮已停止', retryable: false }));
        }
        await task;
        expect(controller.getSnapshot()).toMatchObject(
          scenario === 'complete'
            ? {
                phase: 'complete',
                stopping: false,
                stream: { text: envelope.text, complete: true, revised: true, reviewPending: false },
              }
            : {
                phase: 'interrupted',
                stopping: false,
                stream: { text: '合成部分正文', complete: false, errorCode: 'RUN_CANCELLED' },
              },
        );
        expect(requests.filter((req) => req.path === receipt.events_url)).toHaveLength(1);
        expect(requests.filter((req) => req.method === 'POST')).toHaveLength(scenario === 'cancel' ? 1 : 0);
        expect(requests.every((req) => req.token === 'synthetic-only')).toBe(true);
        expect(JSON.stringify(controller.getSnapshot())).not.toContain('PRIVATE_SENTINEL');
      } finally {
        controller.dispose();
        server.closeAllConnections();
        await new Promise<void>((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
      }
    },
  );
});
