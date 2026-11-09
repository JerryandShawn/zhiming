// @vitest-environment node
// Real loopback HTTP needs Node fetch with its own AbortSignal; jsdom signals are rejected on Node 24.
import { createServer, type IncomingMessage } from 'node:http';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import { describe, expect, it } from 'vitest';
import { threadSubmitPort } from '../src/threads/submit';
import { followThreadEvents } from '../src/threads/follow';

describe('published thread acceptance over real synthetic loopback HTTP', () => {
  it('POST accepts once; GET disconnect/reconnect resumes with actual Last-Event-ID and no repeated projection', async () => {
    const requests: { method?: string; path?: string; cursor?: string }[] = [];
    const runId = 'synthetic-http-stream';
    const envelope = {
      schema: 'core4.0',
      message_id: 'synthetic-message',
      text: '合成最终正文',
      receipts: [],
      used_fact_ids: [],
      used_claim_ids: [],
      asked: null,
      options: null,
      review: { state: 'passed', reasons: [] },
      usage: {},
    };
    const frame = (seq: number, type: string, body: Record<string, unknown>) =>
      `id: ${seq}\nevent: ${type}\ndata: ${JSON.stringify({ v: 1, run_id: runId, seq, ts: '2026-10-27T17:30:00+08:00', ...body })}\n\n`;
    let connections = 0;
    const server = createServer((req, res) => {
      requests.push({ method: req.method, path: req.url, cursor: req.headers['last-event-id'] as string | undefined });
      if (req.url === '/api/threads/life%3Aself/messages' && req.method === 'POST') {
        req.resume();
        res.writeHead(202, { 'Content-Type': 'application/json' });
        res.end(
          JSON.stringify({
            run_id: runId,
            thread_id: 'life:self',
            runtime: 'v4',
            status: 'queued',
            run_url: `/api/runs/${runId}`,
            events_url: `/api/runs/${runId}/events`,
          }),
        );
      } else if (req.url === `/api/runs/${runId}/events` && req.method === 'GET') {
        connections++;
        res.writeHead(200, { 'Content-Type': 'text/event-stream' });
        res.end(
          connections === 1
            ? frame(1, 'text_delta', { text: '待修订' })
            : frame(1, 'text_delta', { text: '重复不得出现' }) +
                ': ping\n\n' +
                frame(3, 'text_reset', { text: '恢复全文', reason: 'resumed' }) +
                frame(5, 'final', { message_id: 'synthetic-message', envelope }),
        );
      } else {
        res.writeHead(404);
        res.end();
      }
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
      const accepted = await threadSubmitPort(fetcher)(
        { threadId: 'life:self', incognito: false },
        { request_id: 'synthetic-http-operation', message: '合成输入' },
        owner,
      );
      const seen: number[] = [];
      const outcome = await followThreadEvents(accepted, {
        ...owner,
        fetcher,
        wait: async () => undefined,
        accept: (event) => {
          seen.push(event.seq);
        },
      });
      expect(outcome).toEqual({ reason: 'final', reconnects: 1, lastEventId: '5' });
      expect(seen).toEqual([1, 3, 5]);
      expect(requests).toEqual([
        { method: 'POST', path: '/api/threads/life%3Aself/messages', cursor: undefined },
        { method: 'GET', path: `/api/runs/${runId}/events`, cursor: undefined },
        { method: 'GET', path: `/api/runs/${runId}/events`, cursor: '1' },
      ]);
    } finally {
      server.closeAllConnections();
      await new Promise<void>((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
    }
  });

  it('sends one authenticated POST, consumes fragmented UTF-8 JSON and adopts returned opaque thread', async () => {
    const requests: {
      path: string | undefined;
      method: string | undefined;
      token: string | undefined;
      body: string;
    }[] = [];
    const server = createServer((req: IncomingMessage, res) => {
      let body = '';
      req.setEncoding('utf8');
      req.on('data', (chunk: string) => {
        body += chunk;
      });
      req.on('end', () => {
        requests.push({ path: req.url, method: req.method, token: String(req.headers['x-token']), body });
        const data = Buffer.from(
          JSON.stringify({
            run_id: 'synthetic-http-run',
            thread_id: 'incognito:合成线程',
            runtime: 'v4',
            status: 'queued',
            run_url: '/api/runs/synthetic-http-run',
            events_url: '/api/runs/synthetic-http-run/events',
          }),
        );
        const split = data.indexOf(Buffer.from('合')) + 1;
        res.writeHead(202, { 'Content-Type': 'application/json; charset=utf-8' });
        res.write(data.subarray(0, split));
        setImmediate(() => res.end(data.subarray(split)));
      });
    });
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const address = server.address() as AddressInfo;
    const base = `http://127.0.0.1:${address.port}`;
    const fetcher: typeof fetch = (path, options) => fetch(new URL(String(path), base), options);
    try {
      const result = await threadSubmitPort(fetcher)(
        { threadId: 'life:self', incognito: false },
        {
          request_id: 'synthetic-http-request',
          message: '合成消息🙂',
        },
        {
          signal: new AbortController().signal,
          isCurrent: () => true,
          headers: () => ({ 'X-Token': 'synthetic-token' }),
        },
      );
      expect(result.thread_id).toBe('incognito:合成线程');
      expect(requests).toHaveLength(1);
      expect(requests[0]).toMatchObject({
        path: '/api/threads/life%3Aself/messages',
        method: 'POST',
        token: 'synthetic-token',
      });
      expect(JSON.parse(requests[0].body)).toEqual({
        request_id: 'synthetic-http-request',
        message: '合成消息🙂',
        subject_id: 'self',
        conversation_id: 'shared',
        case_ids: [],
        depth: 'standard',
      });
    } finally {
      server.closeAllConnections();
      await new Promise<void>((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
    }
  });
});
