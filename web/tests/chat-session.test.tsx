import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { operationNamespace, useAuth } from '../src/api/client';
import { clearPending, loadPending, newPending, readDraft, saveDraft, storePending } from '../src/chat/storage';
import { executeV3 } from '../src/chat/transport';
import type { ChatEvent } from '../src/chat/types';
import { useChat } from '../src/chat/useChat';

function login(token: string) {
  useAuth.getState().setToken(token);
}
function chatHook() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderHook(() => useChat(), {
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
}
afterEach(() => {
  vi.unstubAllGlobals();
  login('');
});
describe('chat session isolation during delayed responses', () => {
  it('preserves ambiguous A and its attachments when restoring historical B, including after refresh', async () => {
    sessionStorage.clear();
    login('');
    const fetcher = vi.fn(async () => {
      throw new TypeError('synthetic ambiguous disconnect');
    });
    vi.stubGlobal('fetch', fetcher);
    const first = chatHook();
    await act(() => first.result.current.send('未确认的 A', ['data:image/png;base64,c3ludGhldGlj']));
    const original = loadPending()!;
    act(() => first.result.current.setText('A 的待补充草稿'));
    act(() =>
      first.result.current.restore({
        role: 'user',
        content: '历史 B',
        at: '2026-10-18T01:00:00Z',
        source: 'web',
        cursor: 'cursor-B',
        turn_id: 'turn-B',
        run_id: 'run-B',
        status: 'failed',
      }),
    );
    expect(first.result.current.error).toMatch(/先处理尚未完成.*明确开始新一轮/);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(loadPending()).toEqual(original);
    expect(readDraft()).toBe('A 的待补充草稿');
    first.unmount();
    const requests: { path: string; body?: string }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (path: string, options?: RequestInit) => {
        requests.push({ path, body: options?.body as string | undefined });
        return path.startsWith('/api/runs/')
          ? Response.json({}, { status: 404 })
          : new Response('data: {"type":"result","result":{"answer":"A 已确认完成"}}\n\n');
      }),
    );
    const refreshed = chatHook();
    expect(refreshed.result.current.pending).toEqual(original);
    expect(refreshed.result.current.draft).toBe('A 的待补充草稿');
    await act(() => refreshed.result.current.retry());
    const submitted = requests.find((request) => request.path === '/api/chat');
    expect(JSON.parse(submitted!.body!)).toEqual(original.payload);
    expect(requests.some((request) => request.path.includes('run-B'))).toBe(false);
    await waitFor(() => expect(loadPending()).toBeUndefined());
  });
  it('restores the same pending run with its original ID and attachments instead of creating a new intent', async () => {
    sessionStorage.clear();
    login('');
    const original = newPending('本轮 A', ['data:image/png;base64,c3ludGhldGlj']);
    original.runId = 'run-A';
    storePending(original);
    const fetcher = vi.fn(async () => {
      throw new TypeError('synthetic ambiguous disconnect');
    });
    vi.stubGlobal('fetch', fetcher);
    const hook = chatHook();
    await act(async () =>
      hook.result.current.restore({
        role: 'user',
        content: '本轮 A 的历史显示文本',
        at: '2026-10-18T01:00:00Z',
        source: 'web',
        cursor: 'cursor-A',
        turn_id: original.payload.request_id,
        run_id: 'run-A',
        status: 'failed',
      }),
    );
    await waitFor(() => expect(hook.result.current.busy).toBe(false));
    expect(fetcher).toHaveBeenCalledWith('/api/runs/run-A', expect.anything());
    expect(loadPending()).toEqual(original);
    expect(hook.result.current.pending).toEqual(original);
    expect(hook.result.current.error).not.toMatch(/先处理尚未完成/);
  });
  it('does not let an old session overwrite or clear the new owner pending request or draft', () => {
    login('synthetic-A');
    const first = newPending('A 合成问题', []),
      scopeA = operationNamespace();
    login('synthetic-B');
    const second = newPending('B 合成问题', []);
    saveDraft('B 草稿');
    expect(() => storePending({ ...first, runId: 'late-A' })).toThrow();
    expect(clearPending(first)).toBe(false);
    saveDraft('', scopeA);
    expect(loadPending()?.payload.request_id).toBe(second.payload.request_id);
    expect(readDraft()).toBe('B 草稿');
  });
  it('checks the request ID before clearing even within the same login namespace', () => {
    login('synthetic-A');
    const first = newPending('旧一轮', []),
      second = newPending('明确新一轮', []);
    expect(clearPending(first)).toBe(false);
    expect(() => storePending(first)).toThrow();
    expect(loadPending()?.payload.request_id).toBe(second.payload.request_id);
  });
  it('ignores a late raw SSE 401 instead of locking the newly authenticated owner', async () => {
    login('synthetic-A');
    const first = newPending('A 合成问题', []);
    let deliver: (response: Response) => void = () => undefined;
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            deliver = resolve;
          }),
      ),
    );
    const request = executeV3(first, false, () => undefined, new AbortController().signal);
    login('synthetic-B');
    const second = newPending('B 合成问题', []);
    deliver(Response.json({}, { status: 401 }));
    await expect(request).rejects.toMatchObject({ name: 'AbortError' });
    expect(useAuth.getState().loginRequired).toBe(false);
    expect(loadPending()?.payload.request_id).toBe(second.payload.request_id);
  });
  it('rejects delayed started/final frames without depending on browser abort delivery', async () => {
    login('synthetic-A');
    const first = newPending('A 合成问题', []);
    let deliver: ReadableStreamDefaultController<Uint8Array> | undefined;
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            new ReadableStream<Uint8Array>({
              start(controller) {
                deliver = controller;
              },
            }),
          ),
      ),
    );
    const events: ChatEvent[] = [];
    const request = executeV3(first, false, (event) => events.push(event), new AbortController().signal);
    await Promise.resolve();
    await Promise.resolve();
    login('synthetic-B');
    const second = newPending('B 合成问题', []);
    deliver!.enqueue(
      new TextEncoder().encode(
        'data: {"type":"started","run_id":"late-A"}\n\ndata: {"type":"result","result":{"answer":"A private answer"}}\n\n',
      ),
    );
    deliver!.close();
    await expect(request).rejects.toMatchObject({ name: 'AbortError' });
    expect(events).toEqual([]);
    expect(loadPending()?.payload.request_id).toBe(second.payload.request_id);
    expect(loadPending()?.runId).toBe(second.runId);
  });
});
