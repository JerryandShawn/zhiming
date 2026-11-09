// @vitest-environment node
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { DraftApiError, writeIntent } from '../src/modules/draftApi';
import { createOrganizeFakeFetch, organizeFakeSeed } from '../src/organize/fakeServer';
import { organizeHttpPort } from '../src/organize/http';

type Handler = (req: IncomingMessage, body: string, res: ServerResponse) => void;
const json = (res: ServerResponse, status: number, value: unknown) => {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(value));
};
const source = { message_id: 'synthetic:m1', revision: 1, start: 0, end: 2 };
const proposal = {
  ...organizeFakeSeed,
  source_refs: [source],
  topics: [{ ...organizeFakeSeed.topics[0]!, source_refs: [source] }],
};
const receipt = (_request_id: string, revision: number, write_status = 'updated') => ({
  operation_id: 'synthetic:op1',
  write_status,
  entity_id: 'synthetic:b1',
  revision,
});
const review = {
  receipt_id: 'synthetic:review1',
  batch_id: 'synthetic:b1',
  revision: 2,
  plan_fingerprint: 'a'.repeat(64),
  reviewed_at: '2026-10-27T17:00:00+08:00',
  expires_at: '2026-10-28T17:00:00+08:00',
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
const port = () => organizeHttpPort((path, init) => fetch(new URL(String(path), base), init));

describe('organize draft HTTP port', () => {
  it('strictly reads proposals and parses review, apply and revert results', async () => {
    handler = (req, body, res) => {
      const requestId = (JSON.parse(body || '{}') as { request_id?: string }).request_id ?? 'none';
      if (req.method === 'GET') return json(res, 200, { items: [proposal], next_cursor: null });
      if (req.url === '/api/organize/synthetic%3Ab1/review')
        return json(res, 200, { ok: true, request_id: requestId, receipt: receipt(requestId, 2), review });
      if (req.url === '/api/organize/apply/synthetic%3Ab1')
        return json(res, 200, {
          ok: true,
          request_id: requestId,
          receipt: receipt(requestId, 3),
          change_id: 'synthetic:change1',
        });
      return json(res, 200, {
        ok: true,
        request_id: requestId,
        receipt: receipt(requestId, 4, 'undone'),
        restored_count: 1,
        conflicts: [],
      });
    };
    const p = port();
    expect((await p.listProposals({ limit: 10, batch_id: 'synthetic:b1' }, owner())).items).toEqual([proposal]);
    const reviewed = await p.review(
      'synthetic:b1',
      writeIntent(1, { plan_fingerprint: 'a'.repeat(64), accepted: true as const }),
      owner(),
    );
    expect(reviewed.review).toEqual(review);
    const applied = await p.apply(
      'synthetic:b1',
      writeIntent(2, { plan_fingerprint: 'a'.repeat(64), review_receipt_id: 'synthetic:review1' }),
      owner(),
    );
    expect(applied.change_id).toBe('synthetic:change1');
    expect(
      (await p.revert('synthetic:b1', writeIntent(3, { change_id: applied.change_id }), owner())).restored_count,
    ).toBe(1);
    expect(requests.map((item) => [item.method, item.url])).toEqual([
      ['GET', '/api/organize/proposal?limit=10&batch_id=synthetic%3Ab1'],
      ['POST', '/api/organize/synthetic%3Ab1/review'],
      ['POST', '/api/organize/apply/synthetic%3Ab1'],
      ['POST', '/api/organize/revert/synthetic%3Ab1'],
    ]);
  });

  it.each([
    ['unknown proposal field', { ...proposal, owner: 'private' }],
    ['non-record-only gate', { ...proposal, quality_gate: 'open' }],
    ['bad topic range', { ...proposal, topics: [{ ...proposal.topics[0]!, start_at: '2026-10-28T17:00:00+08:00' }] }],
  ])('rejects %s', async (_name, item) => {
    handler = (_req, _body, res) => json(res, 200, { items: [item], next_cursor: null });
    await expect(port().listProposals({}, owner())).rejects.toMatchObject({ code: 'BAD_RESPONSE' });
  });

  it.each([
    ['wrong expiry', { expires_at: '2026-10-29T17:00:00+08:00' }],
    ['another batch', { batch_id: 'synthetic:b2' }],
    ['another plan', { plan_fingerprint: 'b'.repeat(64) }],
  ])('rejects a review receipt with %s', async (_name, override) => {
    handler = (_req, body, res) => {
      const requestId = (JSON.parse(body) as { request_id: string }).request_id;
      json(res, 200, {
        ok: true,
        request_id: requestId,
        receipt: receipt(requestId, 2),
        review: { ...review, ...override },
      });
    };
    await expect(
      port().review('synthetic:b1', writeIntent(1, { plan_fingerprint: 'a'.repeat(64), accepted: true }), owner()),
    ).rejects.toMatchObject({ code: 'BAD_RESPONSE' });
  });
});

describe('organize synthetic draft service', () => {
  it('edits and reviews the exact plan but never bypasses record_only', async () => {
    const p = organizeHttpPort(createOrganizeFakeFetch());
    const before = (await p.listProposals({}, owner())).items[0]!;
    const intent = writeIntent(1, {
      edits: [{ kind: 'rename' as const, target_id: 'synthetic:t1', title: '改名草稿' }],
    });
    await p.edit(before.batch_id, intent, owner());
    const edited = (await p.listProposals({}, owner())).items[0]!;
    expect(edited.revision).toBe(2);
    expect(edited.topics[0]!.title).toBe('改名草稿');
    await expect(
      p.review(before.batch_id, writeIntent(2, { plan_fingerprint: before.plan_fingerprint, accepted: true }), owner()),
    ).rejects.toMatchObject({ code: 'REVIEW_PLAN_CHANGED' });
    const granted = await p.review(
      before.batch_id,
      writeIntent(2, { plan_fingerprint: edited.plan_fingerprint, accepted: true }),
      owner(),
    );
    await expect(
      p.apply(
        before.batch_id,
        writeIntent(3, { plan_fingerprint: edited.plan_fingerprint, review_receipt_id: granted.review.receipt_id }),
        owner(),
      ),
    ).rejects.toMatchObject({ code: 'QUALITY_GATE_CLOSED' });
    expect(organizeFakeSeed.topics[0]!.title).toBe('合成话题');
  });

  it('replays identical writes and rejects changed payloads with the same request ID', async () => {
    const p = organizeHttpPort(createOrganizeFakeFetch());
    const intent = writeIntent(1, { edits: [{ kind: 'rename' as const, target_id: 'synthetic:t1', title: '同名' }] });
    const first = await p.edit('synthetic:b1', intent, owner());
    expect(await p.edit('synthetic:b1', intent, owner())).toEqual(first);
    const changed = writeIntent(
      1,
      { edits: [{ kind: 'rename' as const, target_id: 'synthetic:t1', title: '不同' }] },
      intent.request_id,
    );
    await expect(p.edit('synthetic:b1', changed, owner())).rejects.toMatchObject({ code: 'IDEMPOTENCY_CONFLICT' });
  });

  it('rejects invalid or owner-injecting writes before fetch', async () => {
    let calls = 0;
    const p = organizeHttpPort((...args) => {
      calls++;
      return createOrganizeFakeFetch()(...args);
    });
    expect(() => p.suggest(writeIntent(1, { subject_id: 'synthetic:s1', source_refs: [source] }), owner())).toThrow(
      DraftApiError,
    );
    expect(() =>
      p.edit(
        'synthetic:b1',
        writeIntent(1, { edits: [{ kind: 'merge' as const, target_id: 't', target_ids: ['a', 'b'] }] }),
        owner(),
      ),
    ).toThrow(DraftApiError);
    await expect(
      p.revert(
        'synthetic:b1',
        { ...writeIntent(1, { change_id: 'synthetic:c1' }), owner: 'private' } as never,
        owner(),
      ),
    ).rejects.toThrow(DraftApiError);
    expect(calls).toBe(0);
  });
});
