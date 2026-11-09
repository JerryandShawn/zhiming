// @vitest-environment node
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { writeIntent } from '../src/modules/draftApi';
import { createStudyProgressFakeFetch } from '../src/study/progressFakeServer';
import { studyProgressHttpPort, type StudyProgress } from '../src/study/progressHttp';

type Handler = (req: IncomingMessage, body: string, res: ServerResponse) => void;
const json = (res: ServerResponse, status: number, value: unknown) => {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(value));
};
const progress: StudyProgress = {
  lesson_id: 'synthetic:l1',
  lesson_version: 'v1',
  revision: 1,
  status: 'in_progress',
  bookmark: '第二段',
};
let handler: Handler;
let requests: { method?: string; url?: string; body: string }[];
let server: ReturnType<typeof createServer>;
let base: string;
beforeEach(async () => {
  requests = [];
  server = createServer((req, res) => {
    let body = '';
    req.setEncoding('utf8');
    req.on('data', (part: string) => (body += part));
    req.on('end', () => {
      requests.push({ method: req.method, url: req.url, body });
      handler(req, body, res);
    });
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});
afterEach(async () => {
  server.closeAllConnections();
  await new Promise<void>((resolve) => server.close(() => resolve()));
});
const owner = () => ({ signal: new AbortController().signal, isCurrent: () => true, headers: () => ({}) });
const port = () => studyProgressHttpPort((path, init) => fetch(new URL(String(path), base), init));

describe('study progress over loopback HTTP', () => {
  it('uses PUT with expected revision and binds the result to the lesson', async () => {
    let saved = false;
    handler = (req, body, res) => {
      if (req.method === 'PUT') {
        saved = true;
        const requestId = (JSON.parse(body) as { request_id: string }).request_id;
        return json(res, 200, {
          ok: true,
          request_id: requestId,
          receipt: { operation_id: 'synthetic:op1', write_status: 'saved', entity_id: 'synthetic:l1', revision: 1 },
        });
      }
      json(res, 200, saved ? { progress, revision: 1 } : { progress: null, revision: 0 });
    };
    const p = port();
    expect(await p.read('synthetic:l1', owner())).toEqual({ progress: null, revision: 0 });
    const intent = writeIntent(0, { lesson_version: 'v1', status: 'in_progress' as const, bookmark: '第二段' });
    expect((await p.put('synthetic:l1', intent, owner())).write_status).toBe('saved');
    expect(await p.read('synthetic:l1', owner())).toEqual({ progress, revision: 1 });
    expect(requests.map((item) => [item.method, item.url])).toEqual([
      ['GET', '/api/study/progress/synthetic%3Al1'],
      ['PUT', '/api/study/progress/synthetic%3Al1'],
      ['GET', '/api/study/progress/synthetic%3Al1'],
    ]);
  });

  it.each([
    ['null progress with a revision', { progress: null, revision: 1 }],
    ['outer revision mismatch', { progress, revision: 2 }],
    ['another lesson', { progress: { ...progress, lesson_id: 'synthetic:l2' }, revision: 1 }],
    ['injected content', { progress: { ...progress, content: '不能注入教材' }, revision: 1 }],
  ])('rejects %s', async (_name, body) => {
    handler = (_req, _body, res) => json(res, 200, body);
    await expect(port().read('synthetic:l1', owner())).rejects.toMatchObject({ code: 'BAD_RESPONSE' });
  });
});

describe('study progress synthetic service', () => {
  it('creates revision one, replays the same write and preserves progress after conflicts', async () => {
    const p = studyProgressHttpPort(createStudyProgressFakeFetch());
    const intent = writeIntent(0, { lesson_version: 'v1', status: 'in_progress' as const, bookmark: '第二段' });
    const first = await p.put('synthetic:l1', intent, owner());
    expect(first.revision).toBe(1);
    expect(await p.put('synthetic:l1', intent, owner())).toEqual(first);
    expect((await p.read('synthetic:l1', owner())).progress).toMatchObject({ bookmark: '第二段', revision: 1 });
    await expect(
      p.put(
        'synthetic:l1',
        writeIntent(0, { lesson_version: 'v1', status: 'completed' as const, bookmark: null }),
        owner(),
      ),
    ).rejects.toMatchObject({ code: 'REVISION_CONFLICT', currentRevision: 1 });
    await expect(
      p.put(
        'synthetic:l1',
        writeIntent(1, { lesson_version: 'v2', status: 'completed' as const, bookmark: null }),
        owner(),
      ),
    ).rejects.toMatchObject({ code: 'REVISION_CONFLICT', currentRevision: 1 });
    expect((await p.read('synthetic:l1', owner())).progress).toMatchObject({
      status: 'in_progress',
      bookmark: '第二段',
    });
    const changed = writeIntent(
      1,
      { lesson_version: 'v1', status: 'completed' as const, bookmark: null },
      intent.request_id,
    );
    await expect(p.put('synthetic:l1', changed, owner())).rejects.toMatchObject({ code: 'IDEMPOTENCY_CONFLICT' });
  });

  it('keeps lessons isolated and rejects invalid writes before fetch', async () => {
    let calls = 0;
    const fake = createStudyProgressFakeFetch({ lessons: { 'synthetic:l1': 'v1', 'synthetic:l2': 'v3' } });
    const p = studyProgressHttpPort((...args) => {
      calls++;
      return fake(...args);
    });
    await p.put(
      'synthetic:l2',
      writeIntent(0, { lesson_version: 'v3', status: 'completed' as const, bookmark: null }),
      owner(),
    );
    expect(await p.read('synthetic:l1', owner())).toEqual({ progress: null, revision: 0 });
    await expect(
      p.put(
        'synthetic:l1',
        {
          ...writeIntent(0, { lesson_version: 'v1', status: 'completed' as const, bookmark: null }),
          owner: 'x',
        } as never,
        owner(),
      ),
    ).rejects.toThrow();
    await expect(p.read('../l1', owner())).rejects.toThrow();
    expect(calls).toBe(2);
  });
});
