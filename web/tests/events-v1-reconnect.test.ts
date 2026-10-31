import { describe, expect, it, vi } from 'vitest';
import { followV1, type FollowV1ConnectionState, type FollowV1Options } from '../src/chat/followV1';
import { readSse } from '../src/chat/sse';
import { reduceChat } from '../src/chat/reducer';
import { initialStream, type ChatEvent } from '../src/chat/types';

const runId = 'synthetic-follow-run';
const common = { v: 1, run_id: runId, ts: '2026-10-21T08:00:00+08:00' };
const started = { thread_id: 'synthetic-thread', message_id: 'synthetic-message', incognito: false };
const envelope = (text = '确认正文') => ({
  schema: 'core4.0',
  message_id: 'synthetic-message',
  text,
  receipts: [],
  used_fact_ids: [],
  used_claim_ids: [],
  asked: null,
  options: null,
  review: { state: 'passed', reasons: [] },
  usage: {},
});
function frame(
  seq: number,
  type: string,
  body: Record<string, unknown>,
  changes: Record<string, unknown> = {},
  id = String(seq),
) {
  return `id: ${id}\r\nevent: ${type}\r\ndata: ${JSON.stringify({ ...common, seq, ...body, ...changes })}\r\n\r\n`;
}
const first = () => frame(1, 'started', started);
const final = (seq: number, text = '确认正文') =>
  frame(seq, 'final', { message_id: 'synthetic-message', envelope: envelope(text) });
function response(
  chunks: (string | Uint8Array)[],
  options: { open?: boolean; broken?: boolean; cancel?: () => void | Promise<void> } = {},
) {
  let index = 0;
  return new Response(
    new ReadableStream<Uint8Array>({
      pull(controller) {
        if (index < chunks.length) {
          const chunk = chunks[index++];
          controller.enqueue(typeof chunk === 'string' ? new TextEncoder().encode(chunk) : chunk);
        } else if (options.broken) controller.error(new Error('synthetic transport failure'));
        else if (!options.open) controller.close();
      },
      cancel: options.cancel,
    }),
  );
}
function options(extra: Partial<FollowV1Options> = {}): FollowV1Options {
  return {
    signal: new AbortController().signal,
    retryMs: 0,
    wait: async () => undefined,
    connect: async () => response([first(), final(2)]),
    accept: () => undefined,
    ...extra,
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

describe('strict in-memory v1 reconnect follower', () => {
  it('decodes every split UTF-8 byte and split CRLF while heartbeats do not advance the cursor', async () => {
    const bytes = new TextEncoder().encode(
      ': ping\r\n\r\n' + first() + frame(2, 'text_delta', { text: '甲乙，继续。' }) + final(3),
    );
    const accept = vi.fn();
    const result = await followV1(
      runId,
      options({ connect: async () => response(Array.from(bytes, (byte) => Uint8Array.of(byte))), accept }),
    );
    expect(result).toMatchObject({ reason: 'final', lastEventId: '3', reconnects: 0 });
    expect(accept.mock.calls.map(([event]) => event.seq)).toEqual([1, 2, 3]);
    expect(accept.mock.calls[1][0].text).toBe('甲乙，继续。');
  });

  it('passes only the last committed id to the adapter and discards an incomplete disconnected frame', async () => {
    const headers: (string | null)[] = [],
      signals: AbortSignal[] = [],
      seen: ChatEvent[] = [];
    const parts = [
      response([first() + 'id: 2\r\nevent: text_delta\r\ndata: {"text":"未完整']),
      response([frame(2, 'text_delta', { text: '补齐内容' }), final(3)]),
    ];
    const result = await followV1(
      runId,
      options({
        connect: async (cursor, signal) => {
          const requestHeaders = new Headers();
          if (cursor) requestHeaders.set('Last-Event-ID', cursor);
          headers.push(requestHeaders.get('Last-Event-ID'));
          signals.push(signal);
          return parts.shift()!;
        },
        accept: (event) => seen.push(event),
      }),
    );
    expect(headers).toEqual([null, '1']);
    expect(signals.every((signal) => signal instanceof AbortSignal)).toBe(true);
    expect(seen.map((event) => event.seq)).toEqual([1, 2, 3]);
    expect(JSON.stringify(seen)).not.toContain('未完整');
    expect(result).toMatchObject({ reason: 'final', reconnects: 1, lastEventId: '3' });
  });

  it('drops repeated and old sequence ids across reconnects without duplicating text', async () => {
    let state = initialStream();
    const parts = [
      response([first(), frame(2, 'text_delta', { text: '甲' })]),
      response([
        first(),
        frame(2, 'text_delta', { text: '甲' }),
        frame(3, 'text_delta', { text: '乙' }),
        final(4, '甲乙'),
      ]),
    ];
    const connect = vi.fn<FollowV1Options['connect']>(async () => parts.shift()!);
    const accept = vi.fn((event: ChatEvent) => {
      state = reduceChat(state, event);
    });
    expect(await followV1(runId, options({ connect, accept }))).toMatchObject({ reason: 'final', lastEventId: '4' });
    expect(accept.mock.calls.map(([event]) => event.seq)).toEqual([1, 2, 3, 4]);
    expect(state.text).toBe('甲乙');
  });

  it.each([
    ['cross-run', frame(2, 'text_delta', { text: '不能投影' }, { run_id: 'other-run' })],
    ['wrong-id', frame(2, 'text_delta', { text: '不能投影' }, {}, '3')],
    ['noncanonical-id', frame(2, 'text_delta', { text: '不能投影' }, {}, '02')],
    ['legacy', 'id: 2\nevent: text_delta\ndata: {"text":"不能投影"}\n\n'],
    ['bad-json', 'id: 2\nevent: text_delta\ndata: {broken}\n\n'],
    ['wrong-type', frame(2, 'text_delta', { text: '不能投影', type: 'status' })],
  ])('fails closed for %s without cursor advancement or a retry', async (_name, invalid) => {
    const accept = vi.fn(),
      connect = vi.fn<FollowV1Options['connect']>(async () => response([first() + invalid + final(3)]));
    expect(await followV1(runId, options({ accept, connect }))).toMatchObject({
      reason: 'failed',
      code: 'protocol',
      lastEventId: '1',
      reconnects: 0,
    });
    expect(accept).toHaveBeenCalledOnce();
    expect(connect).toHaveBeenCalledOnce();
  });

  it('reconnects from the earlier cursor for a gap and only accepts a continuous replay', async () => {
    const parts = [
      response([first(), frame(3, 'text_delta', { text: '有缺口' })]),
      response([
        frame(2, 'text_delta', { text: '补上第二条' }),
        frame(3, 'text_delta', { text: '再接第三条' }),
        final(4),
      ]),
    ];
    const seen: ChatEvent[] = [],
      connect = vi.fn<FollowV1Options['connect']>(async () => parts.shift()!);
    const result = await followV1(runId, options({ connect, accept: (event) => seen.push(event) }));
    expect(connect.mock.calls[1][0]).toBe('1');
    expect(seen.map((event) => event.seq)).toEqual([1, 2, 3, 4]);
    expect(JSON.stringify(seen)).not.toContain('有缺口');
    expect(result.reason).toBe('final');
  });

  it('never compresses a permanent gap into a cursor, and bounds all retry attempts', async () => {
    const connect = vi.fn<FollowV1Options['connect']>(async () =>
      response([first(), frame(3, 'text_delta', { text: '有缺口' })]),
    );
    const seen: ChatEvent[] = [];
    const result = await followV1(runId, options({ connect, maxReconnects: 2, accept: (event) => seen.push(event) }));
    expect(result).toMatchObject({ reason: 'failed', code: 'sequence_gap', lastEventId: '1', reconnects: 2 });
    expect(connect).toHaveBeenCalledTimes(3);
    expect(seen.map((event) => event.seq)).toEqual([1]);
  });

  it('retries an initial network rejection without inventing wire status or sequence events', async () => {
    const states: FollowV1ConnectionState[] = [],
      seen: ChatEvent[] = [];
    const connect = vi
      .fn()
      .mockRejectedValueOnce(new Error('synthetic network failure'))
      .mockResolvedValueOnce(response([first(), final(2)]));
    const result = await followV1(
      runId,
      options({ connect, accept: (event) => seen.push(event), onConnectionState: (state) => states.push(state) }),
    );
    expect(result).toMatchObject({ reason: 'final', reconnects: 1 });
    expect(connect.mock.calls.map(([cursor]) => cursor)).toEqual([undefined, undefined]);
    expect(states.map(({ phase }) => phase)).toEqual(['connecting', 'reconnecting', 'connecting', 'open', 'closed']);
    expect(seen.map(({ type }) => type)).toEqual(['started', 'final']);
  });

  it('retries a broken response body after the last committed frame', async () => {
    const parts = [
      response([first()], { broken: true }),
      response([frame(2, 'text_delta', { text: '恢复' }), final(3)]),
    ];
    const connect = vi.fn<FollowV1Options['connect']>(async () => parts.shift()!);
    const result = await followV1(runId, options({ connect }));
    expect(result).toMatchObject({ reason: 'final', reconnects: 1, lastEventId: '3' });
    expect(connect.mock.calls[1][0]).toBe('1');
  });

  it('applies resumed text_reset as replacement and keeps it distinct from review revision', async () => {
    let state = initialStream();
    const parts = [
      response([first(), frame(2, 'text_delta', { text: '重复旧片段' })]),
      response([
        frame(2, 'text_delta', { text: '重复旧片段' }),
        frame(3, 'text_reset', { text: '权威恢复正文', reason: 'resumed', revision_id: 'restore-1' }),
        frame(4, 'text_delta', { text: '，继续。' }),
        final(5, '权威恢复正文，继续。'),
      ]),
    ];
    const result = await followV1(
      runId,
      options({
        connect: async () => parts.shift()!,
        accept: (event) => {
          state = reduceChat(state, event);
        },
      }),
    );
    expect(result.reason).toBe('final');
    expect(state).toMatchObject({
      text: '权威恢复正文，继续。',
      revised: false,
      revisionId: 'restore-1',
      complete: true,
    });
  });

  it.each(['final', 'error'] as const)(
    'ends on accepted %s without waiting for EOF or accepting later pollution',
    async (type) => {
      const cancel = vi.fn(),
        seen: ChatEvent[] = [];
      const terminal =
        type === 'final' ? final(2) : frame(2, 'error', { code: 'OFFLINE', message: '请稍后继续。', retryable: true });
      const connect = vi.fn<FollowV1Options['connect']>(async () =>
        response([first() + terminal + frame(3, 'text_delta', { text: '不能追加' })], { open: true, cancel }),
      );
      const result = await followV1(runId, options({ connect, accept: (event) => seen.push(event) }));
      expect(result).toMatchObject({ reason: type, lastEventId: '2' });
      expect(seen.map(({ type }) => type)).toEqual(['started', type]);
      expect(cancel).toHaveBeenCalledOnce();
      expect(connect).toHaveBeenCalledOnce();
    },
  );

  it('awaits acceptance before reading another frame or advancing the cursor', async () => {
    const gate = deferred<void>(),
      seen: number[] = [];
    const job = followV1(
      runId,
      options({
        accept: async (event) => {
          if (event.seq === 1) await gate.promise;
          seen.push(event.seq!);
        },
      }),
    );
    await Promise.resolve();
    await Promise.resolve();
    expect(seen).toEqual([]);
    gate.resolve();
    expect(await job).toMatchObject({ reason: 'final', lastEventId: '2' });
    expect(seen).toEqual([1, 2]);
  });

  it.each(['sync', 'async'])('does not advance or replay a frame rejected by the %s consumer', async (mode) => {
    const seen: number[] = [],
      connect = vi.fn<FollowV1Options['connect']>(async () =>
        response([first(), frame(2, 'text_delta', { text: '不能确认' }), final(3)]),
      );
    const result = await followV1(
      runId,
      options({
        connect,
        accept: (event) => {
          if (event.seq === 2) {
            if (mode === 'async') return Promise.reject(new Error('synthetic consumer failure'));
            throw new Error('synthetic consumer failure');
          }
          seen.push(event.seq!);
        },
      }),
    );
    expect(result).toMatchObject({ reason: 'failed', code: 'consumer', lastEventId: '1', reconnects: 0 });
    expect(seen).toEqual([1]);
    expect(connect).toHaveBeenCalledOnce();
  });

  it('aborts a pending reader immediately and stops old callbacks', async () => {
    const controller = new AbortController(),
      cancel = vi.fn(),
      accept = vi.fn();
    const connect = vi.fn<FollowV1Options['connect']>(async () => response([first()], { open: true, cancel }));
    const task = followV1(runId, options({ signal: controller.signal, connect, accept }));
    await vi.waitFor(() => expect(accept).toHaveBeenCalledOnce());
    controller.abort();
    expect(await task).toMatchObject({ reason: 'aborted' });
    expect(cancel).toHaveBeenCalledOnce();
    expect(connect).toHaveBeenCalledOnce();
    expect(accept).toHaveBeenCalledOnce();
  });

  it('does not wait for an underlying cancel promise that never settles', async () => {
    const controller = new AbortController(),
      cancel = vi.fn(() => new Promise<void>(() => undefined));
    const task = readSse(response([], { open: true, cancel }), vi.fn(), controller.signal);
    controller.abort();
    await expect(task).rejects.toMatchObject({ name: 'AbortError' });
    expect(cancel).toHaveBeenCalledOnce();
  });

  it('aborts a signal-ignoring connector and cancels its late response without calling accept', async () => {
    const controller = new AbortController(),
      gate = deferred<Response>(),
      accept = vi.fn(),
      cancel = vi.fn();
    const task = followV1(runId, options({ signal: controller.signal, connect: () => gate.promise, accept }));
    controller.abort();
    expect(await task).toMatchObject({ reason: 'aborted', lastEventId: undefined });
    gate.resolve(response([first(), final(2)], { open: true, cancel }));
    await vi.waitFor(() => expect(cancel).toHaveBeenCalledOnce());
    expect(accept).not.toHaveBeenCalled();
  });

  it('aborts a signal-ignoring reconnect wait without opening a new generation', async () => {
    const controller = new AbortController(),
      gate = deferred<void>(),
      wait = vi.fn(() => gate.promise);
    const connect = vi.fn<FollowV1Options['connect']>(async () => response([]));
    const task = followV1(runId, options({ signal: controller.signal, connect, wait }));
    await vi.waitFor(() => expect(wait).toHaveBeenCalledOnce());
    controller.abort();
    expect(await task).toMatchObject({ reason: 'aborted', reconnects: 1 });
    gate.resolve();
    await Promise.resolve();
    expect(connect).toHaveBeenCalledOnce();
  });

  it('does not advance after an aborted asynchronous accept resolves late', async () => {
    const controller = new AbortController(),
      gate = deferred<void>(),
      accept = vi.fn(() => gate.promise);
    const task = followV1(runId, options({ signal: controller.signal, accept }));
    await vi.waitFor(() => expect(accept).toHaveBeenCalledOnce());
    controller.abort();
    expect(await task).toMatchObject({ reason: 'aborted', lastEventId: undefined });
    gate.resolve();
    await Promise.resolve();
    await Promise.resolve();
    expect(accept).toHaveBeenCalledOnce();
  });

  it('keeps cursor, deduplication and reconnect state entirely out of browser storage', async () => {
    const get = vi.spyOn(Storage.prototype, 'getItem'),
      set = vi.spyOn(Storage.prototype, 'setItem');
    const remove = vi.spyOn(Storage.prototype, 'removeItem'),
      clear = vi.spyOn(Storage.prototype, 'clear');
    const parts = [response([first()]), response([first(), final(2)])];
    expect(await followV1(runId, options({ connect: async () => parts.shift()! }))).toMatchObject({ reason: 'final' });
    for (const spy of [get, set, remove, clear]) expect(spy).not.toHaveBeenCalled();
  });

  it('does not start a pre-aborted follower or accept an invalid retry budget', async () => {
    const controller = new AbortController(),
      connect = vi.fn();
    controller.abort();
    expect(await followV1(runId, options({ signal: controller.signal, connect }))).toMatchObject({ reason: 'aborted' });
    expect(await followV1(runId, options({ maxReconnects: Infinity, connect }))).toMatchObject({
      reason: 'failed',
      code: 'invalid_config',
    });
    expect(connect).not.toHaveBeenCalled();
  });
});
