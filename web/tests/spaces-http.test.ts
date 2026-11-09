// @vitest-environment node
// Real loopback HTTP needs Node fetch with its own AbortSignal; jsdom signals are rejected on Node 24.
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { DraftApiError, receiptSaved, writeIntent } from '../src/modules/draftApi';
import { spacesTopicsHttpPort } from '../src/spaces/http';

type Handler = (req: IncomingMessage, body: string, res: ServerResponse) => void;
const json = (res: ServerResponse, status: number, value: unknown) => {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(value));
};
const space = {
  id: 'daily',
  revision: 1,
  name: '日常',
  description: '',
  order: 0,
  hidden: false,
  sensitive: false,
};
const topic = {
  id: 'synthetic:t1',
  space_id: 'daily',
  revision: 3,
  title: '合成话题',
  status: 'open',
  summary: '',
  source_refs: [{ message_id: 'synthetic:m1', revision: 1, start: 0, end: 2 }],
  case_id: null,
  updated_at: '2026-10-27T17:00:00+08:00',
  summary_until_message_id: null,
  created_at: '2026-10-27T16:00:00+08:00',
  last_at: '2026-10-27T17:00:00+08:00',
};
const receipt = (request_id: string, write_status = 'updated') => ({
  ok: true,
  request_id,
  receipt: { operation_id: 'synthetic:op1', write_status, entity_id: 'synthetic:t1', revision: 4 },
});

let handler: Handler;
let requests: { method?: string; url?: string; token?: string; body: string }[];
let base: string;
let server: ReturnType<typeof createServer>;
beforeEach(async () => {
  requests = [];
  server = createServer((req, res) => {
    let body = '';
    req.setEncoding('utf8');
    req.on('data', (part: string) => (body += part));
    req.on('end', () => {
      requests.push({ method: req.method, url: req.url, token: req.headers['x-token'] as string, body });
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
const owner = (current = () => true) => ({
  signal: new AbortController().signal,
  isCurrent: current,
  headers: () => ({ 'X-Token': 'synthetic-only' }),
});
const port = () => spacesTopicsHttpPort((path, init) => fetch(new URL(String(path), base), init));

describe('spaces/topics draft port over loopback HTTP', () => {
  it('lists spaces and topics with strict projection and encoded query', async () => {
    handler = (req, _body, res) =>
      req.url!.startsWith('/api/spaces/daily/topics')
        ? json(res, 200, { items: [topic], next_cursor: 'c2' })
        : json(res, 200, { items: [space], next_cursor: null });
    const spaces = await port().listSpaces({ include_hidden: true }, owner());
    expect(spaces).toEqual({ items: [space], next_cursor: null });
    const topics = await port().listTopics('daily', { limit: 20, cursor: 'a b' }, owner());
    expect(topics.items[0]).toEqual(topic);
    expect(topics.next_cursor).toBe('c2');
    expect(requests.map((item) => item.url)).toEqual([
      '/api/spaces?include_hidden=true',
      '/api/spaces/daily/topics?limit=20&cursor=a+b',
    ]);
    expect(requests.every((item) => item.token === 'synthetic-only' && item.body === '')).toBe(true);
  });

  it.each([
    ['unknown field', { items: [{ ...space, owner: 'x' }], next_cursor: null }],
    ['duplicate id', { items: [space, space], next_cursor: null }],
    ['bad name', { items: [{ ...space, name: '' }], next_cursor: null }],
    ['missing cursor', { items: [space] }],
  ])('rejects %s in a space list', async (_name, body) => {
    handler = (_req, _body, res) => json(res, 200, body);
    await expect(port().listSpaces({}, owner())).rejects.toMatchObject({ code: 'BAD_RESPONSE' });
  });

  it.each([
    ['other space', { ...topic, space_id: 'career' }],
    ['case without case_id', { ...topic, status: 'case' }],
    ['open with case_id', { ...topic, case_id: 'case:1' }],
    ['created after last', { ...topic, created_at: '2026-10-27T18:00:00+08:00' }],
    ['naive time', { ...topic, last_at: '2026-10-27T17:00:00' }],
    ['empty source range', { ...topic, source_refs: [{ message_id: 'm', revision: 1, start: 2, end: 2 }] }],
  ])('rejects topic with %s', async (_name, item) => {
    handler = (_req, _body, res) => json(res, 200, { items: [item], next_cursor: null });
    await expect(port().listTopics('daily', {}, owner())).rejects.toMatchObject({ code: 'BAD_RESPONSE' });
  });

  it('resends the identical write after an unknown result and only trusts program receipts', async () => {
    let calls = 0;
    handler = (_req, body, res) => {
      calls++;
      const parsed = JSON.parse(body) as { request_id: string };
      if (calls === 1)
        return json(res, 503, {
          ok: false,
          request_id: parsed.request_id,
          error: { code: 'UNKNOWN_RESULT', message: '私有原文 PRIVATE_SENTINEL', retryable: true },
        });
      json(res, 200, receipt(parsed.request_id, calls === 2 ? 'queued' : 'updated'));
    };
    const intent = writeIntent(3, { patch: { status: 'archived' as const } });
    const first = await port()
      .patchTopic('synthetic:t1', intent, owner())
      .catch((error: unknown) => error);
    expect(first).toBeInstanceOf(DraftApiError);
    expect(first).toMatchObject({ code: 'UNKNOWN_RESULT', status: 503, resendSame: true });
    expect(String((first as Error).message)).not.toContain('PRIVATE_SENTINEL');
    const queued = await port().patchTopic('synthetic:t1', intent, owner());
    expect(receiptSaved(queued)).toBe(false);
    const saved = await port().patchTopic('synthetic:t1', intent, owner());
    expect(receiptSaved(saved)).toBe(true);
    expect(new Set(requests.map((item) => item.body)).size).toBe(1);
    expect(JSON.parse(requests[0].body)).toEqual({
      patch: { status: 'archived' },
      request_id: intent.request_id,
      expected_revision: 3,
    });
    expect(requests.every((item) => item.method === 'PATCH' && item.url === '/api/topics/synthetic%3At1')).toBe(true);
  });

  it.each([
    [409, 'REVISION_CONFLICT', { current_revision: 7 }],
    [409, 'IDEMPOTENCY_CONFLICT', {}],
    [501, 'DRAFT_NOT_IMPLEMENTED', {}],
    [403, 'CONSENT_REQUIRED', {}],
    [410, 'SOURCE_REVOKED', {}],
    [429, 'RATE_LIMITED', {}],
  ])('maps %i %s to fixed copy', async (status, code, extra) => {
    handler = (_req, body, res) =>
      json(res, status, {
        ok: false,
        request_id: (JSON.parse(body) as { request_id: string }).request_id,
        error: { code, message: 'PRIVATE_SENTINEL', retryable: code === 'RATE_LIMITED', ...extra },
      });
    const error = (await port()
      .createTopic('daily', writeIntent(0, { title: '合成' }), owner())
      .catch((item: unknown) => item)) as DraftApiError;
    expect(error).toMatchObject({ code, status });
    expect(error.message).not.toContain('PRIVATE_SENTINEL');
    if (code === 'REVISION_CONFLICT') expect(error.currentRevision).toBe(7);
  });

  it('treats malformed errors, html and wrong receipts as unconfirmed', async () => {
    const outcomes: [number, string, string][] = [
      [500, 'text/html', '<p>PRIVATE_SENTINEL</p>'],
      [
        404,
        'application/json',
        JSON.stringify({ ok: false, error: { code: 'NEW_CODE', message: 'x', retryable: false } }),
      ],
      [200, 'application/json', JSON.stringify(receipt('another-request'))],
      [200, 'application/json', JSON.stringify({ ...receipt('r'), ok: 'true' })],
    ];
    let index = 0;
    handler = (_req, _body, res) => {
      const [status, type, body] = outcomes[index++];
      res.writeHead(status, { 'Content-Type': type });
      res.end(body);
    };
    const codes = [];
    for (let i = 0; i < outcomes.length; i++)
      codes.push(
        await port()
          .routeMessage(
            'synthetic:m1',
            writeIntent(1, { space_id: 'daily', topic_id: null, space_secondary: null }, 'r'),
            owner(),
          )
          .catch((error: DraftApiError) => error.code),
      );
    expect(codes).toEqual(['BAD_RESPONSE', 'BAD_RESPONSE', 'BAD_RESPONSE', 'BAD_RESPONSE']);
  });

  it('refuses invalid writes before any request', () => {
    const p = port();
    expect(() => p.createTopic('daily', writeIntent(1, { title: '合成' }), owner())).toThrow(DraftApiError);
    expect(() => p.createTopic('../x', writeIntent(0, { title: '合成' }), owner())).toThrow(DraftApiError);
    expect(() => p.patchTopic('t', writeIntent(1, { patch: { status: 'case' as const } }), owner())).toThrow(
      DraftApiError,
    );
    expect(() => p.patchSpace('daily', writeIntent(1, { patch: {} }), owner())).toThrow(DraftApiError);
    expect(() =>
      p.routeMessage('m', writeIntent(1, { space_id: 'daily', topic_id: null, space_secondary: 'daily' }), owner()),
    ).toThrow(DraftApiError);
    expect(() => writeIntent(-1, {})).toThrow(DraftApiError);
    expect(requests).toHaveLength(0);
  });

  it('drops a response once the owner changes', async () => {
    let current = true;
    handler = (_req, _body, res) => {
      current = false;
      json(res, 200, { items: [space], next_cursor: null });
    };
    await expect(
      port().listSpaces(
        {},
        owner(() => current),
      ),
    ).rejects.toMatchObject({ code: 'OBSOLETE' });
  });
});
