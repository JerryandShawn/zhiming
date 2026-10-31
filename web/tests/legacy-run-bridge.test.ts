import { afterEach, describe, expect, it, vi } from 'vitest';
import { followAcceptedLegacyRun, type LegacyBridgeOptions } from '../src/legacy/bridge';
afterEach(() => vi.useRealTimers());

const receipt = {
  run_id: 'synthetic-run',
  message_id: 'message-1',
  thread_id: 'life:self',
  runtime: 'v4',
  status: 'queued',
  run_url: '/api/runs/synthetic-run',
  events_url: '/api/runs/synthetic-run/events',
};
function fixture(response = Response.json(receipt, { status: 202 })) {
  const controller = new AbortController();
  const body = document.createElement('div');
  body.textContent = '旧页面占位';
  body.classList.add('type-caret');
  const options: LegacyBridgeOptions = {
    response,
    body,
    signal: controller.signal,
    token: 'synthetic-token',
    isCurrent: () => true,
    fetcher: vi.fn<typeof fetch>(),
    onRun: vi.fn(),
    onReady: vi.fn(),
    onFinal: vi.fn(),
    onRetry: vi.fn(),
  };
  return { controller, body, options };
}
function final(text: string) {
  const envelope = {
    schema: 'core4.0',
    message_id: 'message-1',
    text,
    receipts: [],
    used_fact_ids: [],
    used_claim_ids: [],
    asked: null,
    options: null,
    review: { state: 'revised', reasons: [], revision_id: 'rev-1' },
    usage: {},
  };
  return new Response(
    `id: 1\nevent: final\ndata: ${JSON.stringify({
      v: 1,
      run_id: 'synthetic-run',
      seq: 1,
      ts: '2026-10-27T09:10:00+08:00',
      message_id: 'message-1',
      envelope,
    })}\n\n`,
    { headers: { 'Content-Type': 'text/event-stream' } },
  );
}

describe('explicit old-page 202 bridge, legacy response stays untouched', () => {
  it('does not read, transform or fetch anything for the original SSE response', async () => {
    const f = fixture(
      new Response('data: {"type":"result"}\n\n', { headers: { 'Content-Type': 'text/event-stream' } }),
    );
    expect(await followAcceptedLegacyRun(f.options)).toBeUndefined();
    expect(f.options.response.bodyUsed).toBe(false);
    expect(f.options.fetcher).not.toHaveBeenCalled();
    expect(f.body.textContent).toBe('旧页面占位');
  });

  it('accepts authoritative privacy reroute and restores revision label after final host rendering', async () => {
    const f = fixture(Response.json({ ...receipt, thread_id: 'life:' + '合'.repeat(200) }, { status: 202 }));
    f.options.fetcher = vi.fn<typeof fetch>().mockResolvedValue(final('确认后的正文'));
    f.options.onFinal = vi.fn((envelope) => {
      f.body.textContent = envelope.text;
    });
    expect((await followAcceptedLegacyRun(f.options))?.reason).toBe('final');
    expect(f.options.onRun).toHaveBeenCalledWith('synthetic-run');
    expect(f.body.textContent).toBe('确认后的正文已修订');
    expect(f.body.classList.contains('type-caret')).toBe(false);
    expect(f.options.fetcher).toHaveBeenCalledTimes(1);
  });

  it.each([
    { ...receipt, events_url: 'https://foreign.invalid/events' },
    { ...receipt, events_url: '/api/runs/other/events' },
    { ...receipt, events_url: '/api/runs/synthetic-run/events?token=PRIVATE' },
    { ...receipt, runtime: 'v3' },
    { ...receipt, owner: 'PRIVATE_OWNER' },
    { ...receipt, message_id: '' },
  ])('rejects invalid or cross-scope 202 before replacing DOM or opening a GET', async (value) => {
    const f = fixture(Response.json(value, { status: 202 }));
    await expect(followAcceptedLegacyRun(f.options)).rejects.toThrow('回执尚未核对');
    expect(f.options.fetcher).not.toHaveBeenCalled();
    expect(f.body.textContent).toBe('旧页面占位');
  });

  it('invalid JSON/200 is not silently treated as accepted, nor auto-reposted', async () => {
    for (const response of [
      Response.json(receipt),
      new Response('{broken', { status: 202, headers: { 'Content-Type': 'application/json' } }),
    ]) {
      const f = fixture(response);
      await expect(followAcceptedLegacyRun(f.options)).rejects.toThrow();
      expect(f.options.fetcher).not.toHaveBeenCalled();
    }
  });

  it('drops a JSON response whose owner has retired without touching old or new DOM', async () => {
    const f = fixture();
    f.options.isCurrent = () => false;
    expect((await followAcceptedLegacyRun(f.options))?.reason).toBe('aborted');
    expect(f.options.fetcher).not.toHaveBeenCalled();
    expect(f.body.textContent).toBe('旧页面占位');
  });

  it('does not leak broken JSON excerpts or accept an oversized receipt', async () => {
    for (const body of ['{"PRIVATE_RAW":broken}', JSON.stringify({ ...receipt, secret: 'PRIVATE'.repeat(20000) })]) {
      const f = fixture(new Response(body, { status: 202, headers: { 'Content-Type': 'application/json' } }));
      const error = await followAcceptedLegacyRun(f.options).catch((value: unknown) => value);
      expect(error).toBeInstanceOf(Error);
      expect((error as Error).message).not.toContain('PRIVATE');
      expect(f.options.fetcher).not.toHaveBeenCalled();
      expect(f.body.textContent).toBe('旧页面占位');
    }
  });

  it('receipt body that ignores transport abort is bounded at 45 seconds', async () => {
    vi.useFakeTimers();
    const cancelled = vi.fn();
    const f = fixture(
      new Response(new ReadableStream({ cancel: cancelled }), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const pending = followAcceptedLegacyRun(f.options).catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(45000);
    expect(await pending).toBeInstanceOf(Error);
    expect(cancelled).toHaveBeenCalled();
    expect(f.options.fetcher).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});
