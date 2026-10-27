import { describe, expect, it, vi } from 'vitest';
import { createThreadController } from '../src/threads/controller';
import type { ThreadAcceptance } from '../src/threads/contracts';

const receipt: ThreadAcceptance = {
  run_id: 'synthetic-controller',
  thread_id: 'life:self',
  status: 'queued',
  runtime: 'v4',
  run_url: '/api/runs/synthetic-controller',
  events_url: '/api/runs/synthetic-controller/events',
};
const final = {
  schema: 'core4.0',
  message_id: 'synthetic-message',
  text: '当前已提交终稿',
  receipts: [],
  used_fact_ids: [],
  used_claim_ids: [],
  asked: null,
  options: null,
  review: { state: 'passed', reasons: [] },
  usage: {},
};
const state = (status = 'running', result: unknown = {}, attempts = 1) => ({
  id: receipt.run_id,
  operation_id: 'synthetic-operation',
  status,
  calls: 0,
  call_limit: 12,
  attempts,
  checkpoint: {},
  dependencies: [],
  error: 'PRIVATE_SENTINEL',
  result,
});
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
function frame(seq: number, type: string, body: Record<string, unknown>) {
  return `id: ${seq}\nevent: ${type}\ndata: ${JSON.stringify({ v: 1, run_id: receipt.run_id, seq, ts: '2026-10-27T18:00:00+08:00', ...body })}\n\n`;
}
const done = (envelope: Record<string, unknown> = final) =>
  frame(5, 'final', { message_id: envelope.message_id, envelope });
const delta = frame(1, 'text_delta', { text: '流式草稿' });
function stream(text: string, open = false) {
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
    { headers: { 'Content-Type': 'text/event-stream' } },
  );
  return { response, cancel, write: (text: string) => writer.enqueue(new TextEncoder().encode(text)) };
}
function fixture(fetcher: typeof fetch, isCurrent = () => true) {
  const abort = new AbortController();
  const controller = createThreadController(receipt, {
    fetcher,
    isCurrent,
    signal: abort.signal,
    headers: () => ({ 'X-Token': 'synthetic-only' }),
    wait: async () => undefined,
    maxReconnects: 0,
  });
  return { controller, abort };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe('owner-bound thread controller', () => {
  it('factory is inert; start is single-flight and terminals are confirmed against committed state', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(state()))
      .mockResolvedValueOnce(stream(delta + done()).response)
      .mockResolvedValueOnce(json(state('succeeded', { ...final, answer: final.text })));
    const { controller } = fixture(fetcher);
    expect(fetcher).not.toHaveBeenCalled();
    const first = controller.start();
    expect(controller.start()).toBe(first);
    await first;
    expect(controller.getSnapshot()).toMatchObject({
      phase: 'complete',
      lastEventId: '5',
      stopping: false,
      stream: { text: final.text, complete: true, receipts: [] },
    });
    expect(fetcher.mock.calls.map(([path, init]) => [path, init?.method])).toEqual([
      [receipt.run_url, 'GET'],
      [receipt.events_url, 'GET'],
      [receipt.run_url, 'GET'],
    ]);
    await controller.start();
    expect(fetcher).toHaveBeenCalledTimes(3);
    controller.dispose();
  });
  it('a terminal idempotent acceptance recovers committed result without opening SSE or writing', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json(state('succeeded', final)));
    const controller = createThreadController(
      { ...receipt, status: 'succeeded' },
      { fetcher, signal: new AbortController().signal, isCurrent: () => true, headers: () => ({}) },
    );
    await controller.start();
    expect(controller.getSnapshot().phase).toBe('complete');
    expect(fetcher).toHaveBeenCalledOnce();
    controller.dispose();
  });
  it('active retry attempts with no published epoch checkpoint never replay seq zero', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json(state('running', {}, 2)));
    const { controller } = fixture(fetcher);
    await controller.start();
    expect(controller.getSnapshot()).toMatchObject({ phase: 'needs_check', stream: { complete: false, text: '' } });
    expect(fetcher).toHaveBeenCalledOnce();
    controller.dispose();
  });
  it('an old error in the stream cannot end a newer active retry', async () => {
    const error = frame(2, 'error', { code: 'RUN_FAILED', message: '旧错误', retryable: true });
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(state()))
      .mockResolvedValueOnce(stream(delta + error).response)
      .mockResolvedValueOnce(json(state('running', {}, 2)));
    const { controller } = fixture(fetcher);
    await controller.start();
    expect(controller.getSnapshot()).toMatchObject({
      phase: 'needs_check',
      stream: { text: '流式草稿', complete: false },
    });
    expect(controller.getSnapshot().stream.errorCode).toBeUndefined();
    expect(fetcher).toHaveBeenCalledTimes(3);
    controller.dispose();
  });
  it('a mismatched final never marks the streamed draft verified', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(state()))
      .mockResolvedValueOnce(stream(delta + done()).response)
      .mockResolvedValueOnce(json(state('succeeded', { ...final, text: '另一份终稿' })));
    const { controller } = fixture(fetcher);
    await controller.start();
    expect(controller.getSnapshot()).toMatchObject({
      phase: 'needs_check',
      stream: { text: '流式草稿', complete: false },
    });
    controller.dispose();
  });
  it('authoritative empty receipts/null cards clear abandoned streamed acknowledgements and questions', async () => {
    const memory = frame(2, 'memory_receipt', {
      fact_id: 'synthetic-fact',
      write_status: 'saved',
      summary: '旧的已记下',
      sensitive: false,
    });
    const ask = frame(3, 'ask_user', {
      ask_id: 'synthetic-ask',
      question: '旧问题',
      options: [],
      allow_free_text: true,
      multi: false,
      why: '合成',
    });
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(state()))
      .mockResolvedValueOnce(stream(delta + memory + ask + done()).response)
      .mockResolvedValueOnce(json(state('succeeded', final)));
    const { controller } = fixture(fetcher);
    await controller.start();
    expect(controller.getSnapshot()).toMatchObject({ phase: 'complete', stream: { receipts: [], decisions: [] } });
    expect(controller.getSnapshot().stream.question).toBeUndefined();
    expect(JSON.stringify(controller.getSnapshot())).not.toContain('旧的已记下');
    controller.dispose();
  });
  it('422 performs one state lookup, retains partial and never resets/reopens SSE', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(state()))
      .mockResolvedValueOnce(new Response('', { status: 422 }))
      .mockResolvedValueOnce(json(state()));
    const { controller } = fixture(fetcher);
    await controller.start();
    expect(controller.getSnapshot().phase).toBe('needs_check');
    expect(fetcher.mock.calls.map(([path]) => path)).toEqual([receipt.run_url, receipt.events_url, receipt.run_url]);
    controller.dispose();
  });
  it('stop publishes pending before a slow ack, deduplicates clicks, then only persistent cancelled interrupts', async () => {
    const live = stream(delta, true),
      gate = deferred<Response>();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(state()))
      .mockResolvedValueOnce(live.response)
      .mockReturnValueOnce(gate.promise)
      .mockResolvedValueOnce(json(state('cancelled')));
    const { controller } = fixture(fetcher);
    const run = controller.start();
    await vi.waitFor(() => expect(controller.getSnapshot().stream.text).toBe('流式草稿'));
    const started = performance.now(),
      stopping = controller.stop();
    expect(controller.stop()).toBe(stopping);
    await vi.waitFor(() => expect(controller.getSnapshot().stopping).toBe(true));
    expect(performance.now() - started).toBeLessThan(2000);
    expect(controller.getSnapshot().phase).toBe('following');
    gate.resolve(json({ ok: true, run_id: receipt.run_id }));
    await stopping;
    await run;
    expect(controller.getSnapshot()).toMatchObject({
      phase: 'interrupted',
      stopping: false,
      stream: { text: '流式草稿', complete: false, errorCode: 'RUN_CANCELLED' },
    });
    expect(fetcher.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
    controller.dispose();
  });
  it('stop racing with completion keeps the committed answer rather than labelling it cancelled', async () => {
    const live = stream(delta, true);
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(state()))
      .mockResolvedValueOnce(live.response)
      .mockResolvedValueOnce(json({ ok: true, run_id: receipt.run_id }))
      .mockResolvedValueOnce(json(state('succeeded', final)));
    const { controller } = fixture(fetcher);
    const task = controller.start();
    await vi.waitFor(() => expect(controller.getSnapshot().stream.text).toBe('流式草稿'));
    await controller.stop();
    await task;
    expect(controller.getSnapshot()).toMatchObject({
      phase: 'complete',
      stopping: false,
      stream: { text: final.text, complete: true },
    });
    expect(controller.getSnapshot().stream.errorCode).toBeUndefined();
    controller.dispose();
  });
  it('ack still running is pending until explicit refresh confirms cancelled', async () => {
    const live = stream(delta, true);
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(state()))
      .mockResolvedValueOnce(live.response)
      .mockResolvedValueOnce(json({ ok: true, run_id: receipt.run_id }))
      .mockResolvedValueOnce(json(state()))
      .mockResolvedValueOnce(json(state('cancelled')));
    const { controller } = fixture(fetcher);
    const task = controller.start();
    await vi.waitFor(() => expect(controller.getSnapshot().stream.text).toBe('流式草稿'));
    await controller.stop();
    expect(controller.getSnapshot()).toMatchObject({ phase: 'following', stopping: true });
    await controller.refresh();
    await task;
    expect(controller.getSnapshot().phase).toBe('interrupted');
    controller.dispose();
  });
  it('owner switching during a signal-ignoring read prevents any follow and exposes only a detached blank snapshot', async () => {
    let current = true;
    const gate = deferred<Response>(),
      fetcher = vi.fn<typeof fetch>().mockReturnValue(gate.promise);
    const { controller } = fixture(fetcher, () => current);
    const change = vi.fn();
    controller.subscribe(change);
    const task = controller.start();
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledOnce());
    const before = change.mock.calls.length;
    current = false;
    gate.resolve(json(state('succeeded', final)));
    await task;
    expect(controller.getSnapshot()).toMatchObject({ phase: 'detached', stream: { text: '', runId: '' } });
    expect(change.mock.calls.length).toBe(before);
    expect(fetcher).toHaveBeenCalledOnce();
    controller.dispose();
  });
  it('dispose aborts subscription, clears the projection, and never calls a cancel endpoint', async () => {
    const live = stream(delta, true),
      fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(json(state())).mockResolvedValueOnce(live.response);
    const { controller } = fixture(fetcher);
    const task = controller.start();
    await vi.waitFor(() => expect(controller.getSnapshot().stream.text).toBe('流式草稿'));
    controller.dispose();
    await task;
    expect(controller.getSnapshot()).toMatchObject({ phase: 'detached', stream: { text: '', runId: '' } });
    expect(live.cancel).toHaveBeenCalled();
    expect(fetcher.mock.calls.every(([, init]) => init?.method === 'GET')).toBe(true);
  });
  it('explicit refresh of revoked authority clears a previously completed result', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(state('succeeded', final)))
      .mockResolvedValueOnce(json(state('revoked')));
    const { controller } = fixture(fetcher);
    await controller.start();
    expect(controller.getSnapshot().stream.complete).toBe(true);
    await controller.refresh();
    expect(controller.getSnapshot()).toMatchObject({
      phase: 'ended',
      stream: { text: '', complete: false, receipts: [], errorCode: 'SOURCE_REVOKED' },
    });
    controller.dispose();
  });
  it('an explicitly refreshed active retry removes old verified status and acknowledgements', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(state('succeeded', final)))
      .mockResolvedValueOnce(json(state('running', {}, 2)));
    const { controller } = fixture(fetcher);
    await controller.start();
    await controller.refresh();
    expect(controller.getSnapshot()).toMatchObject({
      phase: 'needs_check',
      stream: { text: final.text, complete: false, receipts: [] },
    });
    expect(controller.getSnapshot().stream.envelope).toBeUndefined();
    controller.dispose();
  });
  it('private network errors are replaced with fixed text and do not erase an existing projection', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(state()))
      .mockResolvedValueOnce(stream(delta).response);
    const { controller } = fixture(fetcher);
    await controller.start();
    expect(controller.getSnapshot()).toMatchObject({ phase: 'needs_check', stream: { text: '流式草稿' } });
    expect(JSON.stringify(controller.getSnapshot())).not.toContain('PRIVATE_SENTINEL');
    controller.dispose();
  });
  it('reentrant start observers cannot create a second request', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json(state('succeeded', final)));
    const { controller } = fixture(fetcher);
    controller.subscribe(() => {
      void controller.start();
    });
    await controller.start();
    expect(fetcher).toHaveBeenCalledOnce();
    controller.dispose();
  });
  it('reentrant stop observers cannot issue another POST', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ ok: true, run_id: receipt.run_id }))
      .mockResolvedValueOnce(json(state('cancelled')));
    const { controller } = fixture(fetcher);
    controller.subscribe(() => {
      if (controller.getSnapshot().stopping) void controller.stop();
    });
    await controller.stop();
    expect(controller.getSnapshot().phase).toBe('interrupted');
    expect(fetcher.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
    controller.dispose();
  });
  it('a slow earlier preflight cannot overwrite a newer completion confirmed by stop', async () => {
    const earlier = deferred<Response>();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockReturnValueOnce(earlier.promise)
      .mockResolvedValueOnce(json({ ok: true, run_id: receipt.run_id }))
      .mockResolvedValueOnce(json(state('succeeded', final)));
    const { controller } = fixture(fetcher);
    const first = controller.start();
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledOnce());
    await controller.stop();
    earlier.resolve(json(state()));
    await first;
    expect(controller.getSnapshot()).toMatchObject({ phase: 'complete', stream: { text: final.text } });
    expect(fetcher.mock.calls.some(([path]) => path === receipt.events_url)).toBe(false);
    controller.dispose();
  });
  it('a late rejected stop cannot erase completion already confirmed from the stream', async () => {
    const live = stream(delta, true),
      ack = deferred<Response>();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(state()))
      .mockResolvedValueOnce(live.response)
      .mockReturnValueOnce(ack.promise)
      .mockResolvedValueOnce(json(state('succeeded', final)));
    const { controller } = fixture(fetcher);
    const run = controller.start();
    await vi.waitFor(() => expect(controller.getSnapshot().stream.text).toBe('流式草稿'));
    const stopping = controller.stop();
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3));
    live.write(done());
    await run;
    ack.resolve(json('PRIVATE_SENTINEL', 500));
    await stopping;
    expect(controller.getSnapshot()).toMatchObject({
      phase: 'complete',
      stopping: false,
      notice: '',
      stream: { text: final.text },
    });
    controller.dispose();
  });
  it.each([401, 403])(
    'current-owner HTTP %s gets a safe login/permission notice without opening SSE',
    async (status) => {
      const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json('PRIVATE_SENTINEL', status));
      const { controller } = fixture(fetcher);
      await controller.start();
      expect(controller.getSnapshot().phase).toBe('needs_check');
      expect(controller.getSnapshot().notice).toContain('登录');
      expect(JSON.stringify(controller.getSnapshot())).not.toContain('PRIVATE_SENTINEL');
      expect(fetcher).toHaveBeenCalledOnce();
      controller.dispose();
    },
  );
  it('observer exceptions and global storage cannot affect committed state', async () => {
    const get = vi.spyOn(Storage.prototype, 'getItem'),
      set = vi.spyOn(Storage.prototype, 'setItem');
    const remove = vi.spyOn(Storage.prototype, 'removeItem'),
      clear = vi.spyOn(Storage.prototype, 'clear');
    const globalFetch = vi.spyOn(globalThis, 'fetch');
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json(state('succeeded', final)));
    const { controller } = fixture(fetcher);
    controller.subscribe(() => {
      throw new Error('PRIVATE_SENTINEL');
    });
    await controller.start();
    expect(controller.getSnapshot().phase).toBe('complete');
    controller.dispose();
    for (const spy of [get, set, remove, clear, globalFetch]) expect(spy).not.toHaveBeenCalled();
  });
  it('a conflicting final receipt cannot keep a streamed saved acknowledgement visible', async () => {
    const memory = frame(2, 'memory_receipt', {
      fact_id: 'synthetic-fact',
      write_status: 'saved',
      summary: '旧的已记下',
      sensitive: false,
    });
    const wrong = { ...final, receipts: [{ write_status: 'saved', fact_id: 'synthetic-fact' }] };
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(state()))
      .mockResolvedValueOnce(stream(delta + memory + done(wrong)).response)
      .mockResolvedValueOnce(json(state('succeeded', final)));
    const { controller } = fixture(fetcher);
    await controller.start();
    expect(controller.getSnapshot()).toMatchObject({ phase: 'needs_check', stream: { complete: false, receipts: [] } });
    expect(JSON.stringify(controller.getSnapshot())).not.toContain('旧的已记下');
    controller.dispose();
  });
  it('an observer changing owner while a failure notice publishes cannot reject or restore that old view', async () => {
    let current = true;
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json('PRIVATE_SENTINEL', 401));
    const { controller } = fixture(fetcher, () => current);
    controller.subscribe(() => {
      if (controller.getSnapshot().notice.includes('重新登录')) current = false;
    });
    await expect(controller.start()).resolves.toBeUndefined();
    expect(controller.getSnapshot()).toMatchObject({ phase: 'detached', stream: { runId: '', text: '' } });
    expect(fetcher).toHaveBeenCalledOnce();
    controller.dispose();
  });
});
