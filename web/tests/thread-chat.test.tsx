import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useAuth } from '../src/api/client';
import { loadPending } from '../src/chat/storage';
import { executeV3 } from '../src/chat/transport';
import { useThreadChat } from '../src/chat/useThreadChat';
import Chat from '../src/live/Chat';
import type { ThreadAcceptance } from '../src/threads/contracts';

vi.mock('../src/chat/transport', () => ({ executeV3: vi.fn() }));

const acceptance: ThreadAcceptance = {
  run_id: 'synthetic:run1',
  thread_id: 'life:self',
  status: 'queued',
  runtime: 'v4',
  run_url: '/api/runs/synthetic:run1',
  events_url: '/api/runs/synthetic:run1/events',
};
const final = {
  schema: 'core4.0',
  message_id: 'synthetic:message1',
  text: '已提交回答',
  receipts: [],
  used_fact_ids: [],
  used_claim_ids: [],
  asked: null,
  options: null,
  review: { state: 'passed', reasons: [] },
  usage: {},
};
const runState = (status = 'running', result: unknown = {}, attempts = 1) => ({
  id: acceptance.run_id,
  operation_id: 'synthetic:operation1',
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
const frame = (seq: number, type: string, body: Record<string, unknown>) =>
  `id: ${seq}\nevent: ${type}\ndata: ${JSON.stringify({ v: 1, run_id: acceptance.run_id, seq, ts: '2026-10-30T18:00:00+08:00', ...body })}\n\n`;
const done = frame(2, 'final', { message_id: final.message_id, envelope: final });
function stream(text: string, open = false) {
  let writer!: ReadableStreamDefaultController<Uint8Array>;
  const response = new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        writer = controller;
        if (text) controller.enqueue(new TextEncoder().encode(text));
        if (!open) controller.close();
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream' } },
  );
  return { response, write: (text: string) => writer.enqueue(new TextEncoder().encode(text)) };
}
function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {children}
    </QueryClientProvider>
  );
}
const hook = () => renderHook(() => useThreadChat(), { wrapper });

beforeEach(() => {
  sessionStorage.clear();
  location.hash = '#/chat';
  useAuth.setState({ token: '', loginRequired: true });
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('v4 thread chat integration', () => {
  it('submits once, renders the authority-confirmed final and clears only that pending request', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(acceptance, 202))
      .mockResolvedValueOnce(json(runState()))
      .mockResolvedValueOnce(stream(frame(1, 'text_delta', { text: '流式草稿' }) + done).response)
      .mockResolvedValueOnce(json(runState('succeeded', { ...final, answer: final.text })));
    vi.stubGlobal('fetch', fetcher);
    const rendered = hook();
    await act(() => rendered.result.current.send('合成问题', []));
    expect(rendered.result.current.phase).toBe('complete');
    expect(rendered.result.current.state).toMatchObject({ text: final.text, complete: true });
    expect(rendered.result.current.completedTurns).toHaveLength(1);
    expect(rendered.result.current.pending).toBeUndefined();
    expect(loadPending()).toBeUndefined();
    expect(fetcher.mock.calls.map(([path, init]) => [path, init?.method])).toEqual([
      ['/api/threads/life%3Aself/messages', 'POST'],
      [acceptance.run_url, 'GET'],
      [acceptance.events_url, 'GET'],
      [acceptance.run_url, 'GET'],
    ]);
    const submission = JSON.parse(String(fetcher.mock.calls[0]![1]?.body)) as Record<string, unknown>;
    expect(submission).toMatchObject({
      message: '合成问题',
      subject_id: 'self',
      conversation_id: 'shared',
      depth: 'standard',
    });
    expect(submission).not.toHaveProperty('images');
    expect(JSON.stringify(rendered.result.current.state)).not.toContain('PRIVATE_SENTINEL');
  });

  it('uses C3 stop authority and retains partial text and the original pending request', async () => {
    const live = stream(frame(1, 'text_delta', { text: '部分回答' }), true);
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(acceptance, 202))
      .mockResolvedValueOnce(json(runState()))
      .mockResolvedValueOnce(live.response)
      .mockResolvedValueOnce(json({ ok: true, run_id: acceptance.run_id }))
      .mockResolvedValueOnce(json(runState('cancelled')));
    vi.stubGlobal('fetch', fetcher);
    const rendered = hook();
    act(() => void rendered.result.current.send('合成问题', []));
    await waitFor(() => expect(rendered.result.current.state.text).toBe('部分回答'));
    await act(() => rendered.result.current.cancel());
    expect(rendered.result.current.phase).toBe('interrupted');
    expect(rendered.result.current.state).toMatchObject({ text: '部分回答', errorCode: 'RUN_CANCELLED' });
    expect(rendered.result.current.pending?.payload.request_id).toBe(loadPending()?.payload.request_id);
    expect(
      fetcher.mock.calls.filter(
        ([path, init]) => init?.method === 'POST' && path !== '/api/threads/life%3Aself/messages',
      ),
    ).toEqual([[`${acceptance.run_url}/cancel`, expect.objectContaining({ method: 'POST' })]]);
  });

  it('restores a persisted v4 acceptance after refresh without another message POST', async () => {
    const firstFetch = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(acceptance, 202))
      .mockResolvedValueOnce(json(runState('running', {}, 2)));
    vi.stubGlobal('fetch', firstFetch);
    const first = hook();
    await act(() => first.result.current.send('合成问题', []));
    expect(first.result.current.phase).toBe('needs_check');
    expect(loadPending()?.thread?.acceptance).toEqual(acceptance);
    first.unmount();
    const secondFetch = vi.fn<typeof fetch>().mockResolvedValue(json(runState('succeeded', final)));
    vi.stubGlobal('fetch', secondFetch);
    const refreshed = hook();
    await act(() => refreshed.result.current.retry());
    expect(refreshed.result.current.phase).toBe('complete');
    expect(secondFetch.mock.calls.map(([path, init]) => [path, init?.method])).toEqual([[acceptance.run_url, 'GET']]);
  });

  it('keeps attachments on the original v3 transport instead of dropping them from v4', async () => {
    vi.mocked(executeV3).mockImplementation(async (_operation, _retry, accept) => {
      accept({
        type: 'final',
        envelope: { answer: 'v3 附图回答', professional_appendix: '', receipts: [], decisions: [], evidence: [] },
      });
    });
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetcher);
    const rendered = hook();
    await act(() => rendered.result.current.send('带图问题', ['data:image/png;base64,c3ludGhldGlj']));
    expect(executeV3).toHaveBeenCalledOnce();
    expect(vi.mocked(executeV3).mock.calls[0]![0].payload.images).toEqual(['data:image/png;base64,c3ludGhldGlj']);
    expect(fetcher.mock.calls.filter(([path]) => String(path).startsWith('/api/threads/'))).toEqual([]);
  });

  it('renders the actual Chat v4 route through the same controller', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(acceptance, 202))
      .mockResolvedValueOnce(json(runState()))
      .mockResolvedValueOnce(stream(frame(1, 'text_delta', { text: '流式草稿' }) + done).response)
      .mockResolvedValueOnce(json(runState('succeeded', final)));
    vi.stubGlobal('fetch', fetcher);
    render(<Chat transport="v4" />, { wrapper });
    expect(document.querySelector('[data-runtime="thread-v4"]')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: '和明镜说说' }), { target: { value: '页面合成问题' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    expect(await screen.findByText(final.text)).toBeVisible();
    await waitFor(() => expect(loadPending()).toBeUndefined());
  });
});
