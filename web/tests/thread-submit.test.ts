import { afterEach, describe, expect, it, vi } from 'vitest';
import { threadSubmitPort, type SubmissionOwner } from '../src/threads/submit';

const target = { threadId: 'life:合成人物', incognito: false };
const payload = { request_id: 'synthetic-request', message: ' 合成输入\n' };
const acceptance = {
  run_id: 'synthetic-run',
  thread_id: 'incognito:returned',
  status: 'inbox_wait',
  runtime: 'v4',
  run_url: '/api/runs/synthetic-run',
  events_url: '/api/runs/synthetic-run/events',
};
const response = (value: unknown = acceptance, status = 202, contentType = 'application/json; charset=utf-8') =>
  new Response(JSON.stringify(value), { status, headers: { 'Content-Type': contentType } });
function owner(): SubmissionOwner {
  return {
    signal: new AbortController().signal,
    isCurrent: () => true,
    headers: () => ({ 'X-Token': 'synthetic-only' }),
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

describe('explicit thread submit adapter (no automatic follow or resend)', () => {
  it('factory is inert; sends exactly once to encoded original thread, adopts returned identity and does not GET', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response());
    const submit = threadSubmitPort(fetcher);
    expect(fetcher).not.toHaveBeenCalled();
    expect(await submit(target, payload, owner())).toEqual(acceptance);
    expect(fetcher).toHaveBeenCalledTimes(1);
    const [path, options] = fetcher.mock.calls[0];
    expect(path).toBe('/api/threads/life%3A%E5%90%88%E6%88%90%E4%BA%BA%E7%89%A9/messages');
    expect(options).toMatchObject({ method: 'POST', credentials: 'same-origin', redirect: 'error', cache: 'no-store' });
    expect(new Headers(options?.headers).get('X-Token')).toBe('synthetic-only');
    expect(JSON.parse(String(options?.body))).toEqual({
      ...payload,
      subject_id: 'self',
      conversation_id: 'shared',
      case_ids: [],
      depth: 'standard',
    });
  });
  it('unknown attachments and incognito cases fail before reading auth or calling fetch', async () => {
    const fetcher = vi.fn<typeof fetch>();
    const scope = { ...owner(), headers: vi.fn() };
    await expect(
      threadSubmitPort(fetcher)(target, { ...payload, images: ['preserve me'] }, scope),
    ).rejects.toMatchObject({ code: 'input' });
    await expect(
      threadSubmitPort(fetcher)({ ...target, incognito: true }, { ...payload, case_ids: ['case'] }, scope),
    ).rejects.toMatchObject({ code: 'input' });
    expect(scope.headers).not.toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('checks ownership before and after a reentrant headers reader', async () => {
    const fetcher = vi.fn<typeof fetch>();
    let current = true;
    const scope = {
      ...owner(),
      isCurrent: () => current,
      headers: () => {
        current = false;
        return {};
      },
    };
    await expect(threadSubmitPort(fetcher)(target, payload, scope)).rejects.toMatchObject({ code: 'obsolete' });
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('ignores and releases a response arriving after the user switches identity', async () => {
    let current = true;
    const pending = deferred<Response>();
    const cancel = vi.fn();
    const late = new Response(new ReadableStream({ cancel }));
    const fetcher = vi.fn<typeof fetch>().mockReturnValue(pending.promise);
    const task = threadSubmitPort(fetcher)(target, payload, { ...owner(), isCurrent: () => current });
    current = false;
    pending.resolve(late);
    await expect(task).rejects.toMatchObject({ code: 'obsolete' });
    expect(cancel).toHaveBeenCalledOnce();
  });
  it('aborts promptly when fetch ignores signal and releases its eventual response', async () => {
    const controller = new AbortController();
    const pending = deferred<Response>();
    const cancel = vi.fn();
    const task = threadSubmitPort(vi.fn<typeof fetch>().mockReturnValue(pending.promise))(target, payload, {
      ...owner(),
      signal: controller.signal,
    });
    controller.abort();
    await expect(task).rejects.toMatchObject({ code: 'obsolete' });
    pending.resolve(new Response(new ReadableStream({ cancel })));
    await Promise.resolve();
    expect(cancel).toHaveBeenCalledOnce();
  });
  it('never invokes a global login handler on a late 401', async () => {
    let current = true;
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => {
      current = false;
      return response('private body', 401);
    });
    await expect(
      threadSubmitPort(fetcher)(target, payload, { ...owner(), isCurrent: () => current }),
    ).rejects.toMatchObject({ code: 'obsolete' });
  });
  it('rejects ownership change during a delayed body read', async () => {
    let current = true;
    let writer!: ReadableStreamDefaultController<Uint8Array>;
    const cancel = vi.fn();
    const res = new Response(
      new ReadableStream<Uint8Array>({
        start: (stream) => {
          writer = stream;
        },
        cancel,
      }),
      { status: 202, headers: { 'Content-Type': 'application/json' } },
    );
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(res);
    const task = threadSubmitPort(fetcher)(target, payload, { ...owner(), isCurrent: () => current });
    await vi.waitFor(() => expect(res.body?.locked).toBe(true));
    current = false;
    writer.enqueue(new TextEncoder().encode(JSON.stringify(acceptance)));
    writer.close();
    await expect(task).rejects.toMatchObject({ code: 'obsolete' });
    expect(res.body?.locked).toBe(false);
  });
  it.each(['.', '..', 'bad\nthread'])('refuses unsafe target %j before a request', async (threadId) => {
    const fetcher = vi.fn<typeof fetch>();
    await expect(threadSubmitPort(fetcher)({ ...target, threadId }, payload, owner())).rejects.toMatchObject({
      code: 'input',
    });
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('does not read identity headers when already aborted', async () => {
    const controller = new AbortController();
    controller.abort();
    const headers = vi.fn();
    const fetcher = vi.fn<typeof fetch>();
    await expect(
      threadSubmitPort(fetcher)(target, payload, { ...owner(), signal: controller.signal, headers }),
    ).rejects.toMatchObject({ code: 'obsolete' });
    expect(headers).not.toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('rejects invalid UTF-8 rather than accepting replacement characters in identity', async () => {
    const res = new Response(new Uint8Array([0xff]), { status: 202, headers: { 'Content-Type': 'application/json' } });
    await expect(
      threadSubmitPort(vi.fn<typeof fetch>().mockResolvedValue(res))(target, payload, owner()),
    ).rejects.toMatchObject({ code: 'receipt' });
  });
  it.each([200, 401, 403, 409, 422, 500])(
    'rejects HTTP %s without automatic POST retry or private body leakage',
    async (status) => {
      const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response('PRIVATE_SENTINEL', status));
      await expect(threadSubmitPort(fetcher)(target, payload, owner())).rejects.toMatchObject({ code: 'http' });
      expect(fetcher).toHaveBeenCalledTimes(1);
    },
  );
  it.each(['text/event-stream', 'text/html', 'application/jsonp'])(
    'rejects %s instead of guessing the protocol',
    async (type) => {
      await expect(
        threadSubmitPort(vi.fn<typeof fetch>().mockResolvedValue(response(acceptance, 202, type)))(
          target,
          payload,
          owner(),
        ),
      ).rejects.toMatchObject({ code: 'receipt' });
    },
  );
  it.each(['PRIVATE_SENTINEL', '"' + 'x'.repeat(65537) + '"'])(
    'bounds and masks damaged/oversized JSON %#',
    async (body) => {
      const res = new Response(body, { status: 202, headers: { 'Content-Type': 'application/json' } });
      await expect(
        threadSubmitPort(vi.fn<typeof fetch>().mockResolvedValue(res))(target, payload, owner()),
      ).rejects.toMatchObject({ code: 'receipt', message: expect.not.stringContaining('PRIVATE_SENTINEL') });
    },
  );
  it('unknown transport result keeps the original operation unchanged for an explicit same-payload retry', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new Error('PRIVATE_SENTINEL'))
      .mockResolvedValueOnce(response());
    const submit = threadSubmitPort(fetcher);
    await expect(submit(target, payload, owner())).rejects.toMatchObject({ code: 'network' });
    expect(fetcher).toHaveBeenCalledTimes(1);
    await submit(target, payload, owner());
    expect(fetcher.mock.calls[1][0]).toBe(fetcher.mock.calls[0][0]);
    expect(fetcher.mock.calls[1][1]?.body).toBe(fetcher.mock.calls[0][1]?.body);
  });
  it('45-second hung fetch is bounded without sending a replacement operation', async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn<typeof fetch>().mockImplementation(() => new Promise(() => undefined));
    const task = threadSubmitPort(fetcher)(target, payload, owner());
    const check = expect(task).rejects.toMatchObject({ code: 'network' });
    await vi.advanceTimersByTimeAsync(45000);
    await check;
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });
  it('45-second hung body is bounded and unlocks the response without retaining content', async () => {
    vi.useFakeTimers();
    const cancel = vi.fn();
    const res = new Response(new ReadableStream({ cancel }), {
      status: 202,
      headers: { 'Content-Type': 'application/json' },
    });
    const task = threadSubmitPort(vi.fn<typeof fetch>().mockResolvedValue(res))(target, payload, owner());
    const check = expect(task).rejects.toMatchObject({ code: 'network' });
    await vi.advanceTimersByTimeAsync(45000);
    await check;
    expect(cancel).toHaveBeenCalled();
    expect(res.body?.locked).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });
});
