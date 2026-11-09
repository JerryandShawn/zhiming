import { afterEach, describe, expect, it, vi } from 'vitest';
import { executeV3 } from '../src/chat/transport';
import { loadPending, newPending } from '../src/chat/storage';
import { imagesFromFiles } from '../src/chat/Composer';
import type { ChatEvent, PendingChat } from '../src/chat/types';

function response(events: unknown[]) {
  return new Response(events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('') + 'data: [DONE]\n\n');
}
afterEach(() => vi.unstubAllGlobals());
describe('persistent v3 chat operations', () => {
  it('freezes linked tarot and chart selection in the persisted request', () => {
    location.hash =
      '#/chat?case=synthetic-case&draw=synthetic-draw&date=2026-10-21&system=bazi&focus=career&key=day.day_ganzhi';
    const operation = newPending('合成问题', []);
    expect(loadPending()?.payload).toEqual(operation.payload);
    expect(operation.payload).toMatchObject({
      case_ids: ['synthetic-case'],
      draw_id: 'synthetic-draw',
      selection: { date: '2026-10-21', system: 'bazi', systems: ['bazi'], focus: 'career', key: 'day.day_ganzhi' },
    });
    location.hash = '#/chat?date=2026-02-30';
    expect(() => newPending('合成问题', [])).toThrow('日期无效');
    location.hash = '#/chat';
  });
  it('retains the same operation across refresh and replays it after an ambiguous failure', async () => {
    sessionStorage.clear();
    const first = newPending('合成问题', []),
      refreshed = loadPending()!;
    expect(refreshed.payload.request_id).toBe(first.payload.request_id);
    const calls: { path: string; body: string }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (path: string, init?: RequestInit) => {
        calls.push({ path, body: String(init?.body || '') });
        if (path.startsWith('/api/runs/')) return Response.json({}, { status: 404 });
        return response([
          { type: 'started', run_id: 'run-synthetic' },
          { type: 'result', result: { answer: '合成回答' } },
        ]);
      }),
    );
    const seen: ChatEvent[] = [];
    await executeV3(refreshed, true, (event) => seen.push(event), new AbortController().signal);
    expect(JSON.parse(calls[1].body).request_id).toBe(first.payload.request_id);
    expect(seen.map((event) => event.type)).toEqual(['started', 'final']);
  });
  it.each(['succeeded', 'failed', 'running'])('restores a %s run without creating another chat', async (status) => {
    const operation = newPending('合成问题', []);
    operation.runId = 'run-synthetic';
    let queries = 0;
    const requests: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (path: string) => {
        requests.push(path);
        if (path.endsWith('/retry')) return response([{ type: 'result', result: { answer: '恢复回答' } }]);
        queries++;
        return Response.json({
          id: operation.runId,
          operation_id: operation.payload.request_id,
          status: status === 'running' && queries > 1 ? 'succeeded' : status,
          result: { answer: '已保存的回答' },
        });
      }),
    );
    const seen: ChatEvent[] = [];
    await executeV3(operation, true, (event) => seen.push(event), new AbortController().signal);
    expect(requests).not.toContain('/api/chat');
    expect(seen.at(-1)?.type).toBe('final');
    expect(requests.some((path) => path.endsWith('/retry'))).toBe(status === 'failed');
  });
  it('never turns a missing history run into a new model request', async () => {
    const operation: PendingChat = { ...newPending('合成历史', []), restoreOnly: true };
    const fetcher = vi.fn(async () => Response.json({}, { status: 404 }));
    vi.stubGlobal('fetch', fetcher);
    await expect(executeV3(operation, true, () => undefined, new AbortController().signal)).rejects.toThrow();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it('rejects unsafe image types, a fifth card and oversized images before reading', async () => {
    await expect(imagesFromFiles([new File(['x'], 'x.svg', { type: 'image/svg+xml' })])).rejects.toThrow('JPEG');
    await expect(
      imagesFromFiles(Array.from({ length: 5 }, () => new File(['x'], 'x.png', { type: 'image/png' }))),
    ).rejects.toThrow('4');
    const large = new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'large.png', { type: 'image/png' });
    await expect(imagesFromFiles([large])).rejects.toThrow('5MB');
    expect(await imagesFromFiles([new File(['synthetic'], 'image.png', { type: 'image/png' })])).toEqual([
      expect.stringMatching(/^data:image\/png;base64,/),
    ]);
  });
});
