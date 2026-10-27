import { afterEach, describe, expect, it, vi } from 'vitest';
import { followThreadEvents, type ThreadFollowOptions } from '../src/threads/follow';
import type { ThreadAcceptance } from '../src/threads/contracts';
import type { RunEventV1 } from '../src/contracts/runEvents';

const receipt: ThreadAcceptance = {
  run_id: 'synthetic-follow',
  thread_id: 'life:self',
  runtime: 'v4',
  status: 'queued',
  run_url: '/api/runs/synthetic-follow',
  events_url: '/api/runs/synthetic-follow/events',
};
const envelope = {
  schema: 'core4.0',
  message_id: 'synthetic-message',
  text: '最终正文',
  receipts: [],
  used_fact_ids: [],
  used_claim_ids: [],
  asked: null,
  options: null,
  review: { state: 'passed', reasons: [] },
  usage: {},
};
function frame(seq: number, type: string, body: Record<string, unknown>, changes: Record<string, unknown> = {}) {
  return `id: ${seq}\nevent: ${type}\ndata: ${JSON.stringify({ v: 1, run_id: receipt.run_id, seq, ts: '2026-10-27T17:30:00+08:00', ...body, ...changes })}\n\n`;
}
const delta = (seq: number, text = '合成') => frame(seq, 'text_delta', { text });
const final = (seq: number) => frame(seq, 'final', { message_id: 'synthetic-message', envelope });
function stream(text = '', open = false) {
  let writer!: ReadableStreamDefaultController<Uint8Array>;
  const cancel = vi.fn();
  const response = new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        writer = controller;
        if (text) controller.enqueue(new TextEncoder().encode(text));
        if (!open) controller.close();
      },
      cancel,
    }),
    { headers: { 'Content-Type': 'text/event-stream; charset=utf-8' } },
  );
  return { response, cancel, write: (part: string) => writer.enqueue(new TextEncoder().encode(part)) };
}
function options(change: Partial<ThreadFollowOptions> = {}): ThreadFollowOptions {
  return {
    signal: new AbortController().signal,
    isCurrent: () => true,
    headers: () => ({ 'X-Token': 'synthetic-only', 'Last-Event-ID': '999' }),
    fetcher: vi.fn<typeof fetch>().mockResolvedValue(stream(final(1)).response),
    accept: vi.fn(),
    wait: async () => undefined,
    ...change,
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
afterEach(() => vi.useRealTimers());

describe('P3 increasing cursor subscription, isolated from contiguous demo follower', () => {
  it('allows revoked gaps, deduplicates, carries last consumed cursor and lets resumed reset replace text', async () => {
    const parts = [
      stream(delta(1, '旧') + delta(3, '草稿')).response,
      stream(delta(3, '不能重放') + frame(7, 'text_reset', { text: '恢复全文', reason: 'resumed' }) + final(9))
        .response,
    ];
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => parts.shift()!);
    const events: RunEventV1[] = [];
    let text = '';
    const result = await followThreadEvents(
      receipt,
      options({
        fetcher,
        accept: (event) => {
          events.push(event);
          if (event.type === 'text_delta') text += event.text;
          if (event.type === 'text_reset') text = event.text;
          if (event.type === 'final') text = event.envelope.text;
        },
      }),
    );
    expect(result).toEqual({ reason: 'final', reconnects: 1, lastEventId: '9' });
    expect(events.map((event) => event.seq)).toEqual([1, 3, 7, 9]);
    expect(text).toBe('最终正文');
    expect(new Headers(fetcher.mock.calls[0][1]?.headers).get('Last-Event-ID')).toBeNull();
    expect(new Headers(fetcher.mock.calls[1][1]?.headers).get('Last-Event-ID')).toBe('3');
    for (const [url, init] of fetcher.mock.calls) {
      expect(url).toBe(receipt.events_url);
      expect(init).toMatchObject({ method: 'GET', cache: 'no-store', redirect: 'error', credentials: 'same-origin' });
      expect(new Headers(init?.headers).get('X-Token')).toBe('synthetic-only');
    }
  });
  it('422 stops the bad cursor without replaying zero or retrying POST', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(stream(delta(5)).response)
      .mockResolvedValueOnce(new Response('PRIVATE_SENTINEL', { status: 422 }));
    expect(await followThreadEvents(receipt, options({ fetcher }))).toEqual({
      reason: 'needs_state',
      reconnects: 1,
      lastEventId: '5',
      code: 'cursor_unavailable',
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(new Headers(fetcher.mock.calls[1][1]?.headers).get('Last-Event-ID')).toBe('5');
  });
  it.each([
    [401, 'unauthorized'],
    [403, 'forbidden'],
    [404, 'unavailable'],
  ] as const)('HTTP %s is terminal and never leaks its body', async (status, code) => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response('PRIVATE_SENTINEL', { status }));
    expect(await followThreadEvents(receipt, options({ fetcher }))).toEqual({ reason: 'failed', reconnects: 0, code });
    expect(fetcher).toHaveBeenCalledOnce();
  });
  it('503 retries a GET within a fixed budget and retains the same run', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response('', { status: 503 }))
      .mockResolvedValueOnce(stream(final(4)).response);
    expect(await followThreadEvents(receipt, options({ fetcher }))).toMatchObject({
      reason: 'final',
      reconnects: 1,
      lastEventId: '4',
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it('exhaustion stops at the configured reconnect budget', async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => stream().response);
    expect(await followThreadEvents(receipt, options({ fetcher, maxReconnects: 2 }))).toEqual({
      reason: 'failed',
      reconnects: 2,
      code: 'unavailable',
    });
    expect(fetcher).toHaveBeenCalledTimes(3);
  });
  it.each(['text/html', 'application/json'])(
    'refuses a successful %s response without retry or reading it as an SSE stream',
    async (type) => {
      const fetcher = vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response('PRIVATE_SENTINEL', { headers: { 'Content-Type': type } }));
      expect(await followThreadEvents(receipt, options({ fetcher }))).toEqual({
        reason: 'failed',
        reconnects: 0,
        code: 'protocol',
      });
      expect(fetcher).toHaveBeenCalledOnce();
    },
  );
  it.each([
    frame(1, 'text_delta', { text: '合成' }, { run_id: 'other' }),
    delta(1).replace('id: 1', 'id: 2'),
    'id: 1\nevent: text_delta\ndata: PRIVATE_SENTINEL\n\n',
    final(1).replace('"receipts":[]', '"memory_receipts":[]'),
  ])('rejects protocol drift/cross-run/R7 aliases without moving cursor %#', async (text) => {
    const accept = vi.fn();
    expect(
      await followThreadEvents(
        receipt,
        options({ fetcher: vi.fn<typeof fetch>().mockResolvedValue(stream(text).response), accept }),
      ),
    ).toEqual({ reason: 'failed', reconnects: 0, code: 'protocol' });
    expect(accept).not.toHaveBeenCalled();
  });
  it('consumer failure does not advance or reconnect a possibly applied projection', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(stream(delta(2) + final(4)).response);
    expect(
      await followThreadEvents(
        receipt,
        options({
          fetcher,
          accept: () => {
            throw new Error('PRIVATE_SENTINEL');
          },
        }),
      ),
    ).toEqual({ reason: 'failed', reconnects: 0, code: 'consumer' });
    expect(fetcher).toHaveBeenCalledOnce();
  });
  it('does not commit a cursor until an asynchronous consumer completes', async () => {
    const gate = deferred<void>(),
      controller = new AbortController();
    const accept = vi.fn(() => gate.promise);
    const task = followThreadEvents(receipt, options({ signal: controller.signal, accept }));
    await vi.waitFor(() => expect(accept).toHaveBeenCalledOnce());
    controller.abort();
    expect(await task).toEqual({ reason: 'aborted', reconnects: 0 });
    gate.resolve();
    await Promise.resolve();
    expect(accept).toHaveBeenCalledOnce();
  });
  it('ignores and releases a signal-ignoring connector after abort', async () => {
    const pending = deferred<Response>(),
      controller = new AbortController();
    const accept = vi.fn();
    const task = followThreadEvents(
      receipt,
      options({ signal: controller.signal, fetcher: () => pending.promise, accept }),
    );
    controller.abort();
    expect(await task).toEqual({ reason: 'aborted', reconnects: 0 });
    const late = stream(final(1), true);
    pending.resolve(late.response);
    await vi.waitFor(() => expect(late.cancel).toHaveBeenCalledOnce());
    expect(accept).not.toHaveBeenCalled();
  });
  it('checks ownership after reading authentication headers and before GET', async () => {
    let current = true;
    const fetcher = vi.fn<typeof fetch>();
    expect(
      await followThreadEvents(
        receipt,
        options({
          fetcher,
          isCurrent: () => current,
          headers: () => {
            current = false;
            return {};
          },
        }),
      ),
    ).toEqual({ reason: 'aborted', reconnects: 0 });
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('RUN_CANCELLED is an authoritative terminal event that preserves the last event cursor', async () => {
    const accept = vi.fn();
    const text = delta(1) + frame(3, 'error', { code: 'RUN_CANCELLED', message: '本轮已停止', retryable: false });
    expect(
      await followThreadEvents(
        receipt,
        options({ fetcher: vi.fn<typeof fetch>().mockResolvedValue(stream(text).response), accept }),
      ),
    ).toEqual({ reason: 'error', reconnects: 0, lastEventId: '3' });
    expect(accept).toHaveBeenCalledTimes(2);
  });
  it('heartbeat resets the 45-second idle clock but never advances cursor', async () => {
    vi.useFakeTimers();
    const first = stream('', true),
      second = stream(final(5));
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(first.response).mockResolvedValueOnce(second.response);
    const task = followThreadEvents(receipt, options({ fetcher }));
    await vi.advanceTimersByTimeAsync(40000);
    first.write(': ping\n\n');
    await vi.advanceTimersByTimeAsync(40000);
    expect(fetcher).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(5001);
    expect(await task).toEqual({ reason: 'final', reconnects: 1, lastEventId: '5' });
    expect(new Headers(fetcher.mock.calls[1][1]?.headers).get('Last-Event-ID')).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });
  it('wait interruption never starts another GET and never touches browser storage', async () => {
    const controller = new AbortController(),
      gate = deferred<void>();
    const wait = vi.fn(() => gate.promise),
      fetcher = vi.fn<typeof fetch>().mockResolvedValue(stream().response);
    const spies = ['getItem', 'setItem', 'removeItem', 'clear'].map((key) =>
      vi.spyOn(Storage.prototype, key as 'getItem'),
    );
    const task = followThreadEvents(receipt, options({ signal: controller.signal, wait, fetcher }));
    await vi.waitFor(() => expect(wait).toHaveBeenCalledOnce());
    controller.abort();
    expect(await task).toEqual({ reason: 'aborted', reconnects: 1 });
    gate.resolve();
    expect(fetcher).toHaveBeenCalledOnce();
    for (const spy of spies) expect(spy).not.toHaveBeenCalled();
  });
  it('v3 acceptance and invalid configuration never guess an event URL', async () => {
    const fetcher = vi.fn<typeof fetch>();
    const { events_url: omitted, ...base } = receipt;
    expect(omitted).toBeTruthy();
    expect(await followThreadEvents({ ...base, runtime: 'v3' }, options({ fetcher }))).toMatchObject({
      reason: 'failed',
      code: 'invalid_config',
    });
    expect(await followThreadEvents(receipt, options({ fetcher, maxReconnects: Infinity }))).toMatchObject({
      reason: 'failed',
      code: 'invalid_config',
    });
    expect(fetcher).not.toHaveBeenCalled();
  });
  it.each(['succeeded', 'failed', 'stale', 'cancelled', 'revoked'] as const)(
    'terminal idempotent %s receipt requires state rather than zero-cursor replay',
    async (status) => {
      const fetcher = vi.fn<typeof fetch>();
      expect(await followThreadEvents({ ...receipt, status }, options({ fetcher }))).toEqual({
        reason: 'needs_state',
        reconnects: 0,
      });
      expect(fetcher).not.toHaveBeenCalled();
    },
  );
});
