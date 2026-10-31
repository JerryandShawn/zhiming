import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, renderHook, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useAuth } from '../src/api/client';
import { loadPending, newPending, readDraft, saveDraft, storePending } from '../src/chat/storage';
import { executeV3 } from '../src/chat/transport';
import type { ChatEvent, PendingChat } from '../src/chat/types';
import { useChat } from '../src/chat/useChat';
import Chat from '../src/live/Chat';

vi.mock('../src/chat/transport', () => ({ executeV3: vi.fn() }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}
type StreamGate = {
  operation: PendingChat;
  signal: AbortSignal;
  emit: (event: ChatEvent) => void;
  finish: () => void;
};
let streams: StreamGate[];
function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {children}
    </QueryClientProvider>
  );
}
function chatHook() {
  return renderHook(() => useChat(), { wrapper });
}
function start(hook: ReturnType<typeof chatHook>, prompt = '合成问题', runId = 'run-one') {
  let task!: Promise<void>;
  act(() => {
    task = hook.result.current.send(prompt, []);
  });
  const stream = streams.at(-1)!;
  act(() => stream.emit({ type: 'started', run_id: runId }));
  return { stream, task };
}
function final(stream: StreamGate) {
  stream.emit({
    type: 'final',
    envelope: {
      answer: '合成回答',
      professional_appendix: '',
      receipts: [],
      decisions: [],
      evidence: [],
    },
  });
  stream.finish();
}
beforeEach(() => {
  sessionStorage.clear();
  useAuth.setState({ token: '', loginRequired: true });
  streams = [];
  vi.mocked(executeV3).mockImplementation(async (operation, _retry, accept, signal) => {
    const gate = deferred<void>();
    signal.addEventListener('abort', () => gate.reject(new DOMException('Stopped', 'AbortError')), { once: true });
    streams.push({
      operation,
      signal,
      finish: () => gate.resolve(),
      emit: (event) => {
        if (event.type === 'started') {
          operation.runId = event.run_id;
          storePending(operation);
        }
        accept(event);
      },
    });
    return gate.promise;
  });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('v3 cancellation feedback and receipt ownership', () => {
  it('announces the stop immediately even after two seconds without an acknowledgement or a new stream status', async () => {
    vi.useFakeTimers();
    const response = deferred<Response>();
    vi.stubGlobal(
      'fetch',
      vi.fn(() => response.promise),
    );
    render(<Chat />, { wrapper });
    fireEvent.change(screen.getByRole('textbox', { name: '和明镜说说' }), { target: { value: '合成问题' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    const stream = streams[0];
    act(() => stream.emit({ type: 'started', run_id: 'run-one' }));
    fireEvent.click(screen.getByRole('button', { name: '停止回答' }));
    expect(screen.getByText('正在请求停止')).toHaveAttribute('role', 'status');
    act(() => {
      vi.advanceTimersByTime(2501);
      stream.emit({ type: 'status', text: '仍在输出' });
    });
    expect(screen.getByText('正在请求停止')).toBeVisible();
    expect(stream.signal.aborted).toBe(false);
    expect(loadPending()).toBeDefined();
    await act(async () => response.resolve(Response.json({ ok: true, run_id: 'run-one' })));
    expect(stream.signal.aborted).toBe(true);
    expect(screen.getByText('已停止本轮')).toHaveAttribute('role', 'status');
    expect(loadPending()).toBeDefined();
  });

  it.each([
    { status: 422, receipt: {} },
    { status: 200, receipt: { ok: true, run_id: 'foreign-run' } },
    { status: 200, receipt: { ok: false, run_id: 'run-one' } },
  ])(
    'retains the same pending request and retry key for an unconfirmed receipt: $status $receipt',
    async ({ status, receipt }) => {
      const bodies: string[] = [];
      vi.stubGlobal(
        'fetch',
        vi.fn(async (_path: string, init?: RequestInit) => {
          bodies.push(String(init?.body));
          return bodies.length === 1
            ? Response.json(receipt, { status })
            : Response.json({ ok: true, run_id: 'run-one' });
        }),
      );
      const hook = chatHook();
      const { stream } = start(hook);
      const pending = loadPending();
      await act(() => hook.result.current.cancel());
      expect(stream.signal.aborted).toBe(false);
      expect(hook.result.current.busy).toBe(true);
      expect(hook.result.current.stopStatus).toBe('尚未确认停止，可以重试');
      expect(hook.result.current.state.status).not.toBe('已停止本轮');
      expect(hook.result.current.error).toBeTruthy();
      expect(loadPending()).toEqual(pending);
      await act(() => hook.result.current.cancel());
      expect(bodies[1]).toBe(bodies[0]);
      expect(stream.signal.aborted).toBe(true);
      expect(loadPending()).toEqual(pending);
    },
  );

  it('does not abort a subsequent operation when an earlier stop acknowledgement arrives late', async () => {
    const response = deferred<Response>();
    vi.stubGlobal(
      'fetch',
      vi.fn(() => response.promise),
    );
    const hook = chatHook();
    const first = start(hook);
    let stopping!: Promise<void>;
    act(() => {
      stopping = hook.result.current.cancel();
    });
    await act(async () => {
      final(first.stream);
      await first.task;
    });
    const second = start(hook, '下一轮合成问题', 'run-two');
    await act(async () => {
      response.resolve(Response.json({ ok: true, run_id: 'run-one' }));
      await stopping;
    });
    expect(second.stream.signal.aborted).toBe(false);
    expect(hook.result.current.stopStatus).toBe('');
    expect(hook.result.current.state.runId).toBe('run-two');
    expect(loadPending()?.payload.request_id).toBe(second.stream.operation.payload.request_id);
    await act(async () => {
      final(second.stream);
      await second.task;
    });
  });

  it('rejects a receipt for the captured target if that operation has since acquired another run ID', async () => {
    const response = deferred<Response>();
    vi.stubGlobal(
      'fetch',
      vi.fn(() => response.promise),
    );
    const hook = chatHook();
    const { stream, task } = start(hook);
    let stopping!: Promise<void>;
    act(() => {
      stopping = hook.result.current.cancel();
    });
    act(() => stream.emit({ type: 'started', run_id: 'run-replaced' }));
    await act(async () => {
      response.resolve(Response.json({ ok: true, run_id: 'run-one' }));
      await stopping;
    });
    expect(stream.signal.aborted).toBe(false);
    expect(hook.result.current.stopStatus).not.toBe('已停止本轮');
    expect(loadPending()?.runId).toBe('run-replaced');
    await act(async () => {
      final(stream);
      await task;
    });
  });

  it('ignores a delayed acknowledgement after the login namespace changes', async () => {
    useAuth.setState({ token: 'synthetic-owner-a', loginRequired: true });
    const response = deferred<Response>();
    vi.stubGlobal(
      'fetch',
      vi.fn((path: string) =>
        path.startsWith('/api/history') ? Promise.resolve(Response.json([])) : response.promise,
      ),
    );
    const hook = chatHook();
    const { stream } = start(hook);
    let stopping!: Promise<void>;
    act(() => {
      stopping = hook.result.current.cancel();
    });
    act(() => useAuth.getState().setToken('synthetic-owner-b'));
    const next = newPending('另一个登录的合成问题', []);
    saveDraft('另一个登录的草稿');
    await act(async () => {
      response.resolve(Response.json({ ok: true, run_id: 'run-one' }));
      await stopping;
    });
    expect(stream.signal.aborted).toBe(false);
    expect(hook.result.current.stopStatus).not.toBe('已停止本轮');
    expect(loadPending()?.payload.request_id).toBe(next.payload.request_id);
    expect(readDraft()).toBe('另一个登录的草稿');
    hook.unmount();
  });
});

describe('late final draft revision guard', () => {
  it.each(['下一轮的新草稿', '合成问题'])(
    'preserves a newly edited draft even when its value is %s',
    async (nextDraft) => {
      const hook = chatHook();
      act(() => hook.result.current.setText('合成问题'));
      const { stream, task } = start(hook);
      act(() => hook.result.current.setText(nextDraft));
      await act(async () => {
        final(stream);
        await task;
      });
      expect(loadPending()).toBeUndefined();
      expect(hook.result.current.draft).toBe(nextDraft);
      expect(readDraft()).toBe(nextDraft);
      expect(hook.result.current.completedTurns).toHaveLength(1);
    },
  );
});
