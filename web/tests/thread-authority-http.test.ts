import { createServer } from 'node:http';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import { describe, expect, it } from 'vitest';
import { threadAuthorityPort } from '../src/threads/authority';
import { followThreadEvents } from '../src/threads/follow';
import type { ThreadAcceptance } from '../src/threads/contracts';

describe('synthetic loopback persisted state and cancellation', () => {
  it.each(['pending', 'completion-race'] as const)(
    '%s: unavailable cursor reads state; stop ack alone is never stopped',
    async (scenario) => {
      const accepted: ThreadAcceptance = {
        run_id: 'synthetic-authority-http',
        thread_id: 'life:self',
        status: 'running',
        runtime: 'v4',
        run_url: '/api/runs/synthetic-authority-http',
        events_url: '/api/runs/synthetic-authority-http/events',
      };
      const envelope = {
        schema: 'core4.0',
        message_id: 'synthetic-message',
        text: '合成已完成终稿',
        receipts: [],
        used_fact_ids: [],
        used_claim_ids: [],
        asked: null,
        options: null,
        review: { state: 'passed', reasons: [] },
        usage: {},
      };
      let persisted = 'running';
      const requests: { method?: string; path?: string; token?: string; body: string }[] = [];
      const server = createServer((req, res) => {
        let body = '';
        req.setEncoding('utf8');
        req.on('data', (part: string) => {
          body += part;
        });
        req.on('end', () => {
          requests.push({
            method: req.method,
            path: req.url,
            token: req.headers['x-token'] as string | undefined,
            body,
          });
          res.setHeader('Content-Type', 'application/json');
          if (req.method === 'GET' && req.url === accepted.events_url) {
            res.writeHead(422);
            res.end(JSON.stringify({ private: 'PRIVATE_SENTINEL' }));
          } else if (req.method === 'POST' && req.url === `${accepted.run_url}/cancel`) {
            if (scenario === 'completion-race') persisted = 'succeeded';
            res.end(JSON.stringify({ ok: true, run_id: accepted.run_id }));
          } else if (req.method === 'GET' && req.url === accepted.run_url) {
            res.end(
              JSON.stringify({
                id: accepted.run_id,
                operation_id: 'synthetic-operation',
                status: persisted,
                calls: 1,
                call_limit: 12,
                attempts: 1,
                checkpoint: { private: 'PRIVATE_SENTINEL' },
                dependencies: [],
                error: 'PRIVATE_SENTINEL',
                result: persisted === 'succeeded' ? envelope : { private: 'PRIVATE_SENTINEL' },
              }),
            );
          } else {
            res.writeHead(404);
            res.end();
          }
        });
      });
      server.listen(0, '127.0.0.1');
      await once(server, 'listening');
      const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
      const fetcher: typeof fetch = (path, init) => fetch(new URL(String(path), base), init);
      const owner = {
        signal: new AbortController().signal,
        isCurrent: () => true,
        headers: () => ({ 'X-Token': 'synthetic-only' }),
      };
      try {
        expect(
          await followThreadEvents(accepted, {
            ...owner,
            fetcher,
            accept: () => {
              throw new Error('No event expected');
            },
          }),
        ).toEqual({ reason: 'needs_state', reconnects: 0, code: 'cursor_unavailable' });
        const authority = threadAuthorityPort(fetcher);
        expect(await authority.read(accepted, owner)).toEqual({
          runId: accepted.run_id,
          status: 'running',
          attempts: 1,
        });
        const stop = await authority.stop(accepted, owner);
        expect(stop).toEqual({
          acknowledged: true,
          stopped: false,
          state: {
            runId: accepted.run_id,
            status: scenario === 'completion-race' ? 'succeeded' : 'running',
            attempts: 1,
            ...(scenario === 'completion-race' ? { final: envelope } : {}),
          },
        });
        if (scenario === 'pending') persisted = 'cancelled';
        expect(await authority.read(accepted, owner)).toEqual({
          runId: accepted.run_id,
          status: scenario === 'pending' ? 'cancelled' : 'succeeded',
          attempts: 1,
          ...(scenario === 'completion-race' ? { final: envelope } : {}),
        });
        expect(requests.map(({ method, path }) => [method, path])).toEqual([
          ['GET', accepted.events_url],
          ['GET', accepted.run_url],
          ['POST', `${accepted.run_url}/cancel`],
          ['GET', accepted.run_url],
          ['GET', accepted.run_url],
        ]);
        for (const req of requests) {
          expect(req.token).toBe('synthetic-only');
          expect(req.body).toBe('');
        }
        expect(JSON.stringify(stop)).not.toContain('PRIVATE_SENTINEL');
      } finally {
        server.closeAllConnections();
        await new Promise<void>((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
      }
    },
  );
});
