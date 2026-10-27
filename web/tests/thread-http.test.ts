import { createServer, type IncomingMessage } from 'node:http';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import { describe, expect, it } from 'vitest';
import { threadSubmitPort } from '../src/threads/submit';

describe('published thread acceptance over real synthetic loopback HTTP', () => {
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
