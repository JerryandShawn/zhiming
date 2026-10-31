import { afterEach, describe, expect, it, vi } from 'vitest';
import { runState, threadAuthorityPort } from '../src/threads/authority';
import { runStates, type ThreadAcceptance } from '../src/threads/contracts';
import { ownedJson, type RequestOwner } from '../src/threads/request';

const accepted: ThreadAcceptance = {
  run_id: 'synthetic-authority',
  thread_id: 'life:self',
  runtime: 'v4',
  status: 'queued',
  run_url: '/api/runs/synthetic-authority',
  events_url: '/api/runs/synthetic-authority/events',
};
const envelope = {
  schema: 'core4.0',
  message_id: 'synthetic-message',
  text: '已确认的合成终稿',
  receipts: [],
  used_fact_ids: [],
  used_claim_ids: [],
  asked: null,
  options: null,
  review: { state: 'passed', reasons: [] },
  usage: {},
};
const row = (status = 'running', result: unknown = { private: 'PRIVATE_SENTINEL' }) => ({
  id: accepted.run_id,
  operation_id: 'synthetic-operation',
  status,
  calls: 1,
  call_limit: 12,
  attempts: 1,
  checkpoint: { private: 'PRIVATE_SENTINEL' },
  dependencies: ['PRIVATE_SENTINEL'],
  error: 'PRIVATE_SENTINEL',
  result,
});
const response = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const owner = (): RequestOwner => ({
  signal: new AbortController().signal,
  isCurrent: () => true,
  headers: () => ({ 'X-Token': 'synthetic-only' }),
});
afterEach(() => vi.useRealTimers());

describe('persistent run projection is authority, never private raw run data', () => {
  it.each(runStates.filter((state) => state !== 'succeeded'))(
    '%s never reads an old partial result or raw failure text',
    (status) => {
      const value = row(status);
      for (const key of ['result', 'checkpoint', 'dependencies', 'error'])
        Object.defineProperty(value, key, {
          enumerable: true,
          get: () => {
            throw new Error('PRIVATE_SENTINEL');
          },
        });
      expect(runState(value, accepted.run_id)).toEqual({ runId: accepted.run_id, status, attempts: 1 });
    },
  );
  it('only exposes a strict succeeded core4 result, retaining receipts from its own field', () => {
    const final = { ...envelope, receipts: [{ write_status: 'saved', fact_id: 'synthetic-fact' }] };
    expect(runState(row('succeeded', final), accepted.run_id)).toEqual({
      runId: accepted.run_id,
      status: 'succeeded',
      attempts: 1,
      final,
    });
    expect(JSON.stringify(runState(row('succeeded', final), accepted.run_id))).not.toContain('PRIVATE_SENTINEL');
  });
  it.each([
    null,
    {},
    { ...envelope, schema: 'core3.0' },
    { ...envelope, memory_receipts: [] },
    { ...envelope, receipts: null },
    {
      ...envelope,
      meta: {
        core_run: { run_id: 'other', operation_id: 'synthetic-operation' },
        subject_id: 'self',
        case_ids: [],
        structural_warnings: [],
      },
    },
    {
      ...envelope,
      meta: {
        core_run: { run_id: accepted.run_id, operation_id: 'other' },
        subject_id: 'self',
        case_ids: [],
        structural_warnings: [],
      },
    },
  ])('rejects malformed/legacy/cross-run succeeded result %#', (result) => {
    expect(() => runState(row('succeeded', result), accepted.run_id)).toThrow('回执尚未核对');
  });
  it.each([
    { ...row(), id: 'other' },
    { ...row(), status: 'finished' },
    { ...row(), attempts: -1 },
    { ...row(), calls: '1' },
    { ...row(), call_limit: -1 },
    { ...row(), operation_id: '../x' },
    { ...row(), owner: 'unexpected' },
  ])('rejects structural drift before returning any state %#', (value) => {
    expect(() => runState(value, accepted.run_id)).toThrow('回执尚未核对');
  });
  it('keeps attempt count for the future epoch-aware controller rather than resetting it', () => {
    expect(runState({ ...row(), attempts: 3 }, accepted.run_id).attempts).toBe(3);
  });
  it('accepts a valid zero-call budget rather than inventing a positive minimum', () => {
    expect(runState({ ...row(), calls: 0, call_limit: 0 }, accepted.run_id)).toEqual({
      runId: accepted.run_id,
      status: 'running',
      attempts: 1,
    });
    expect(() => runState({ ...row(), calls: 2, call_limit: 1 }, accepted.run_id)).toThrow();
  });
});

describe('explicit same-run authority transport', () => {
  it.each([
    'https://example.invalid/run',
    '//example.invalid/run',
    '/api/runs/a/../b',
    '/api/runs/a?cursor=1',
    '/api/runs/a#x',
    '/api/runs/a\\b',
  ])('shared request refuses unsafe %s before auth or transport', async (path) => {
    const fetcher = vi.fn<typeof fetch>();
    const scope = { ...owner(), headers: vi.fn() };
    await expect(ownedJson(fetcher, path, { method: 'GET', status: 200, maxBytes: 8192 }, scope)).rejects.toMatchObject(
      { code: 'input' },
    );
    expect(fetcher).not.toHaveBeenCalled();
    expect(scope.headers).not.toHaveBeenCalled();
  });
  it('construction is inert; read GETs one verified URL, projects away raw data and never resends chat', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response(row()));
    const port = threadAuthorityPort(fetcher);
    expect(fetcher).not.toHaveBeenCalled();
    expect(await port.read(accepted, owner())).toEqual({ runId: accepted.run_id, status: 'running', attempts: 1 });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe(accepted.run_url);
    expect(fetcher.mock.calls[0][1]).toMatchObject({
      method: 'GET',
      redirect: 'error',
      cache: 'no-store',
      credentials: 'same-origin',
    });
    expect(fetcher.mock.calls[0][1]?.body).toBeUndefined();
    expect(new Headers(fetcher.mock.calls[0][1]?.headers).get('X-Token')).toBe('synthetic-only');
  });
  it.each(runStates)('cancel ack followed by %s only says stopped for persistent cancelled', async (status) => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(response({ ok: true, run_id: accepted.run_id }))
      .mockResolvedValueOnce(response(row(status, status === 'succeeded' ? envelope : undefined)));
    const result = await threadAuthorityPort(fetcher).stop(accepted, owner());
    expect(result).toMatchObject({ acknowledged: true, stopped: status === 'cancelled', state: { status } });
    expect(result.state.final).toEqual(status === 'succeeded' ? envelope : undefined);
    expect(fetcher.mock.calls.map(([path, init]) => [path, init?.method])).toEqual([
      [`${accepted.run_url}/cancel`, 'POST'],
      [accepted.run_url, 'GET'],
    ]);
    expect(fetcher.mock.calls[0][1]?.body).toBeUndefined();
  });
  it.each([
    null,
    {},
    { ok: false, run_id: accepted.run_id },
    { ok: true, run_id: 'other' },
    { ok: true, run_id: accepted.run_id, stopped: true },
  ])('invalid ack never initiates a state GET %#', async (ack) => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response(ack));
    await expect(threadAuthorityPort(fetcher).stop(accepted, owner())).rejects.toMatchObject({ code: 'receipt' });
    expect(fetcher).toHaveBeenCalledOnce();
  });
  it.each([401, 403, 404, 422, 500])('read HTTP %s is safe, classifiable and never auto-retries', async (status) => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response('PRIVATE_SENTINEL', status));
    await expect(threadAuthorityPort(fetcher).read(accepted, owner())).rejects.toMatchObject({
      code: 'http',
      status,
      message: expect.not.stringContaining('PRIVATE_SENTINEL'),
    });
    expect(fetcher).toHaveBeenCalledOnce();
  });
  it('ambiguous cancel transport failure does not GET, POST again or call any delete route', async () => {
    const fetcher = vi.fn<typeof fetch>().mockRejectedValue(new Error('PRIVATE_SENTINEL'));
    await expect(threadAuthorityPort(fetcher).stop(accepted, owner())).rejects.toMatchObject({ code: 'network' });
    expect(fetcher).toHaveBeenCalledOnce();
  });
  it('owner switching during ack body consumption prevents the second authenticated request', async () => {
    let current = true;
    let writer!: ReadableStreamDefaultController<Uint8Array>;
    const res = new Response(
      new ReadableStream<Uint8Array>({
        start: (stream) => {
          writer = stream;
        },
      }),
      { headers: { 'Content-Type': 'application/json' } },
    );
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(res);
    const task = threadAuthorityPort(fetcher).stop(accepted, { ...owner(), isCurrent: () => current });
    await vi.waitFor(() => expect(res.body?.locked).toBe(true));
    current = false;
    writer.enqueue(new TextEncoder().encode(JSON.stringify({ ok: true, run_id: accepted.run_id })));
    writer.close();
    await expect(task).rejects.toMatchObject({ code: 'obsolete' });
    expect(fetcher).toHaveBeenCalledOnce();
    expect(res.body?.locked).toBe(false);
  });
  it.each(['read', 'stop'] as const)(
    '%s rejects a forged cross-origin acceptance or v3 before reading auth',
    async (method) => {
      const fetcher = vi.fn<typeof fetch>();
      const scope = { ...owner(), headers: vi.fn() };
      await expect(
        threadAuthorityPort(fetcher)[method]({ ...accepted, run_url: 'https://example.invalid/run' }, scope),
      ).rejects.toMatchObject({ code: 'receipt' });
      const { events_url: omitted, ...base } = accepted;
      expect(omitted).toBeTruthy();
      await expect(threadAuthorityPort(fetcher)[method]({ ...base, runtime: 'v3' }, scope)).rejects.toMatchObject({
        code: 'input',
      });
      expect(fetcher).not.toHaveBeenCalled();
      expect(scope.headers).not.toHaveBeenCalled();
    },
  );
  it.each(['read', 'stop'] as const)('%s bounds JSON before private data can escape', async (method) => {
    const size = method === 'read' ? 2097153 : 8193;
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response('x'.repeat(size)));
    await expect(threadAuthorityPort(fetcher)[method](accepted, owner())).rejects.toMatchObject({ code: 'receipt' });
    expect(fetcher).toHaveBeenCalledOnce();
  });
});
