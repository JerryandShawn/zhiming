import { afterEach, describe, expect, it, vi } from 'vitest';
import { subscribeLegacyRun, type LegacyRunOptions } from '../src/legacy/followRun';

afterEach(() => vi.useRealTimers());
const runId = 'synthetic-legacy-run';
function frame(seq: number, type: string, payload: Record<string, unknown>, id = String(seq)) {
  return `id: ${id}\nevent: ${type}\ndata: ${JSON.stringify({ v: 1, run_id: runId, seq, ts: '2026-10-27T09:10:00+08:00', ...payload })}\n\n`;
}
const delta = (seq: number, text: string) => frame(seq, 'text_delta', { text });
const final = (seq: number, text: string) =>
  frame(seq, 'final', {
    message_id: 'message-1',
    envelope: {
      schema: 'core4.0',
      message_id: 'message-1',
      text,
      receipts: [],
      used_fact_ids: [],
      used_claim_ids: [],
      asked: null,
      options: null,
      review: { state: 'passed', reasons: [] },
      usage: {},
    },
  });
function stream(text = '', open = false) {
  let writer: ReadableStreamDefaultController<Uint8Array>;
  const cancel = vi.fn();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      writer = controller;
      if (text) controller.enqueue(new TextEncoder().encode(text));
      if (!open) controller.close();
    },
    cancel,
  });
  return {
    response: new Response(body, { headers: { 'Content-Type': 'text/event-stream; charset=utf-8' } }),
    write: (value: string) => writer.enqueue(new TextEncoder().encode(value)),
    cancel,
  };
}
function fixture(fetcher: typeof fetch) {
  const controller = new AbortController();
  const elements = {
    answer: document.createElement('div'),
    status: document.createElement('p'),
    review: document.createElement('span'),
    interrupted: document.createElement('span'),
  };
  elements.interrupted.hidden = true;
  let owner = true;
  const options: LegacyRunOptions = {
    runId,
    elements,
    fetcher,
    headers: { 'X-Token': 'synthetic-token' },
    signal: controller.signal,
    isCurrent: () => owner,
  };
  return { options, controller, elements, retire: () => (owner = false) };
}
async function flush() {
  for (let i = 0; i < 20; i++) await Promise.resolve();
}

describe('legacy GET follower, no original POST replay', () => {
  it('reconnects three times using committed cursor and drops replayed duplicates', async () => {
    vi.useFakeTimers();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(stream(delta(1, '甲')).response)
      .mockResolvedValueOnce(stream(delta(1, '甲') + delta(2, '乙')).response)
      .mockResolvedValueOnce(stream(delta(2, '乙') + delta(3, '丙')).response)
      .mockResolvedValueOnce(stream(delta(3, '丙') + final(4, '甲乙丙')).response);
    const f = fixture(fetcher),
      session = subscribeLegacyRun(f.options);
    await vi.advanceTimersByTimeAsync(1600);
    expect(await session.done).toEqual({ reason: 'final', lastEventId: '4' });
    expect(f.elements.answer.textContent).toBe('甲乙丙');
    expect(fetcher).toHaveBeenCalledTimes(4);
    expect(fetcher.mock.calls.map(([, init]) => new Headers(init?.headers).get('Last-Event-ID'))).toEqual([
      null,
      '1',
      '2',
      '3',
    ]);
    for (const [url, init] of fetcher.mock.calls) {
      expect(url).toBe(`/api/runs/${runId}/events`);
      expect(init).toMatchObject({ method: 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error' });
    }
    expect(vi.getTimerCount()).toBe(0);
  });

  it('discards residual UTF-8/CRLF frame on EOF without committing its ID', async () => {
    vi.useFakeTimers();
    const partial = delta(2, '乙').slice(0, -2);
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(stream(delta(1, '甲') + partial).response)
      .mockResolvedValueOnce(stream(delta(2, '乙') + final(3, '甲乙')).response);
    const f = fixture(fetcher),
      session = subscribeLegacyRun(f.options);
    await vi.advanceTimersByTimeAsync(510);
    expect((await session.done).reason).toBe('final');
    expect(new Headers(fetcher.mock.calls[1][1]?.headers).get('Last-Event-ID')).toBe('1');
    expect(f.elements.answer.textContent).toBe('甲乙');
  });

  it('45 seconds without valid frame or ping aborts only the connection and resumes cursor', async () => {
    vi.useFakeTimers();
    const quiet = stream(delta(1, '部分'), true);
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(quiet.response)
      .mockResolvedValueOnce(stream(final(2, '部分完整')).response);
    const f = fixture(fetcher),
      session = subscribeLegacyRun(f.options);
    await flush();
    await vi.advanceTimersByTimeAsync(44999);
    expect(fetcher).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(501);
    expect((await session.done).reason).toBe('final');
    expect(quiet.cancel).toHaveBeenCalled();
    expect(new Headers(fetcher.mock.calls[1][1]?.headers).get('Last-Event-ID')).toBe('1');
    expect(f.elements.answer.textContent).toBe('部分完整');
  });

  it('ping refreshes the idle deadline without advancing Last-Event-ID', async () => {
    vi.useFakeTimers();
    const quiet = stream(delta(1, '甲'), true),
      fetcher = vi.fn<typeof fetch>().mockResolvedValue(quiet.response);
    const f = fixture(fetcher),
      session = subscribeLegacyRun(f.options);
    await flush();
    await vi.advanceTimersByTimeAsync(30000);
    quiet.write(': ping\n\n');
    await flush();
    await vi.advanceTimersByTimeAsync(44000);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(session.snapshot().lastEventId).toBe('1');
    session.dispose();
    expect((await session.done).reason).toBe('aborted');
    expect(vi.getTimerCount()).toBe(0);
  });

  it.each([401, 403, 404, 422])('HTTP %s stops without resetting cursor, replay or reading body', async (status) => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response('PRIVATE_SERVER_BODY', { status }));
    const f = fixture(fetcher),
      session = subscribeLegacyRun(f.options);
    expect((await session.done).reason).toBe('failed');
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(f.elements.status.textContent).not.toContain('PRIVATE');
  });

  it('does not accept malformed IDs, wrong run, HTML or silently skip a sequence gap', async () => {
    vi.useFakeTimers();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(stream(delta(1, '甲') + delta(3, '丙')).response)
      .mockResolvedValueOnce(stream(delta(2, '乙') + final(3, '甲乙')).response);
    const f = fixture(fetcher),
      session = subscribeLegacyRun(f.options);
    await vi.advanceTimersByTimeAsync(510);
    expect((await session.done).reason).toBe('final');
    expect(f.elements.answer.textContent).toBe('甲乙');
    expect(new Headers(fetcher.mock.calls[1][1]?.headers).get('Last-Event-ID')).toBe('1');
  });

  it('cancel HTTP ack preserves partial text, until authoritative RUN_CANCELLED', async () => {
    const open = stream(delta(1, '已出的部分'), true);
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(open.response)
      .mockResolvedValueOnce(new Response('{}'));
    const f = fixture(fetcher),
      session = subscribeLegacyRun(f.options);
    await flush();
    const stop = session.stop();
    expect(f.elements.status.textContent).toBe('正在停止…');
    expect(await stop).toBe(true);
    expect(f.elements.interrupted.hidden).toBe(true);
    expect(f.elements.answer.textContent).toBe('已出的部分');
    expect(fetcher.mock.calls[1][0]).toBe(`/api/runs/${runId}/cancel`);
    open.write(frame(2, 'error', { code: 'RUN_CANCELLED', message: '已停止', retryable: false }));
    expect((await session.done).reason).toBe('cancelled');
    expect(f.elements.interrupted.textContent).toBe('已中断');
    expect(f.elements.answer.textContent).toBe('已出的部分');
  });

  it('stop request ignored by transport gives feedback in two seconds, not false cancellation', async () => {
    vi.useFakeTimers();
    const open = stream(delta(1, '部分'), true);
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(open.response)
      .mockImplementationOnce(() => new Promise(() => {}));
    const f = fixture(fetcher),
      session = subscribeLegacyRun(f.options);
    await flush();
    const stopped = session.stop();
    await vi.advanceTimersByTimeAsync(2000);
    expect(await stopped).toBe(false);
    expect(f.elements.status.textContent).toContain('停止尚未确认');
    expect(f.elements.interrupted.hidden).toBe(true);
    session.dispose();
    await session.done;
    expect(vi.getTimerCount()).toBe(0);
  });

  it('retires late response after owner switch and cancels its body without DOM writes', async () => {
    let resolve!: (response: Response) => void;
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(() => new Promise<Response>((accept) => (resolve = accept)));
    const f = fixture(fetcher),
      session = subscribeLegacyRun(f.options),
      response = stream(delta(1, '不属于新登录'));
    f.retire();
    resolve(response.response);
    expect((await session.done).reason).toBe('aborted');
    expect(f.elements.answer.textContent).toBe('');
    expect(response.cancel).toHaveBeenCalled();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
