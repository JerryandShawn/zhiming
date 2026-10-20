import { StrictMode, useEffect, type PropsWithChildren } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useRecovery } from '../src/night/recovery/useRecovery';
import type { RecoveryPort } from '../src/night/recovery/types';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
}
function events(runId: string, text: string, factId: string, terminal = true) {
  const frame = (seq: number, type: string, body: Record<string, unknown>) =>
    `id: ${seq}\r\nevent: ${type}\r\ndata: ${JSON.stringify({ v: 1, run_id: runId, seq, ts: '2026-10-21T02:00:00+08:00', ...body })}\r\n\r\n`;
  const first =
    frame(1, 'started', { thread_id: 'synthetic-thread', message_id: 'synthetic-message', incognito: false }) +
    frame(2, 'text_delta', { text }) +
    frame(3, 'memory_receipt', {
      fact_id: factId,
      write_status: 'undone',
      sensitive: false,
      summary: '合成偏好已撤销',
    });
  return terminal
    ? first +
        frame(4, 'final', {
          message_id: 'synthetic-message',
          envelope: {
            schema: 'core4.0',
            message_id: 'synthetic-message',
            text,
            receipts: [{ fact_id: factId, write_status: 'undone' }],
            used_fact_ids: [],
            used_claim_ids: [],
            asked: null,
            options: null,
            review: { state: 'passed', reasons: [] },
            usage: { offline: true },
          },
        })
    : first;
}
function stream(
  runId: string,
  text: string,
  factId: string,
  options: { terminal?: boolean; open?: boolean; canceled?: () => void } = {},
) {
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(events(runId, text, factId, options.terminal ?? true)));
        if (!options.open) controller.close();
      },
      cancel: options.canceled,
    }),
    { headers: { 'Content-Type': 'text/event-stream' } },
  );
}
const port = (runId: string, connect: RecoveryPort['connect']): RecoveryPort => ({ runId, connect, mode: 'memory' });

describe('recovery view ownership with the real strict follower and SSE reader', () => {
  it('keeps the stopped view aborted when a signal-ignoring connection returns text and receipts late', async () => {
    const run = 'synthetic-stopped-run',
      gate = deferred<Response>(),
      canceled = deferred<void>();
    const connect = vi.fn<RecoveryPort['connect']>(() => gate.promise);
    const supplied = port(run, connect);
    const { result } = renderHook(() => useRecovery(supplied));
    await waitFor(() => expect(connect).toHaveBeenCalledOnce());
    act(() => result.current.stop());
    expect(result.current.connection.phase).toBe('aborted');
    expect(result.current.running).toBe(false);
    const stopped = result.current.state;
    await act(async () => {
      gate.resolve(
        stream(run, '停止后不可出现的旧正文', 'synthetic-stopped-fact', {
          open: true,
          canceled: () => canceled.resolve(),
        }),
      );
      await canceled.promise;
    });
    expect(result.current.connection.phase).toBe('aborted');
    expect(result.current.state).toBe(stopped);
    expect(result.current.state.text).toBe('');
    expect(result.current.state.receipts).toEqual([]);
    expect(result.current.result).toBeUndefined();
    expect(connect.mock.calls[0][1].aborted).toBe(true);
  });

  it('finishes a replay before the previous connector resolves, then preserves the new text and receipt', async () => {
    const run = 'synthetic-replayed-run',
      old = deferred<Response>(),
      oldCanceled = deferred<void>();
    const connect = vi
      .fn<RecoveryPort['connect']>()
      .mockImplementationOnce(() => old.promise)
      .mockResolvedValueOnce(stream(run, '新轮已确认正文', 'synthetic-new-fact'));
    const supplied = port(run, connect);
    const { result } = renderHook(() => useRecovery(supplied));
    await waitFor(() => expect(connect).toHaveBeenCalledOnce());
    act(() => result.current.replay());
    await waitFor(() => expect(result.current.result?.reason).toBe('final'));
    expect(result.current.state.text).toBe('新轮已确认正文');
    expect(result.current.state.receipts.map(({ fact_id }) => fact_id)).toEqual(['synthetic-new-fact']);
    const confirmed = result.current.state;
    await act(async () => {
      old.resolve(
        stream(run, '迟到旧轮正文', 'synthetic-old-fact', { open: true, canceled: () => oldCanceled.resolve() }),
      );
      await oldCanceled.promise;
    });
    expect(result.current.state).toBe(confirmed);
    expect(result.current.connection.phase).toBe('closed');
    expect(result.current.result).toMatchObject({ reason: 'final', lastEventId: '4' });
    expect(connect).toHaveBeenCalledTimes(2);
    expect(connect.mock.calls[0][1].aborted).toBe(true);
    expect(connect.mock.calls[1][1].aborted).toBe(false);
  });

  it('isolates a supplied-port run change from a late response belonging to the previous run', async () => {
    const old = deferred<Response>(),
      oldCanceled = deferred<void>();
    const oldConnect = vi.fn<RecoveryPort['connect']>(() => old.promise);
    const newConnect = vi.fn<RecoveryPort['connect']>(async () =>
      stream('synthetic-new-run', '新运行的公开正文', 'synthetic-new-run-fact'),
    );
    const first = port('synthetic-old-run', oldConnect),
      second = port('synthetic-new-run', newConnect);
    const { result, rerender } = renderHook(({ supplied }: { supplied: RecoveryPort }) => useRecovery(supplied), {
      initialProps: { supplied: first },
    });
    await waitFor(() => expect(oldConnect).toHaveBeenCalledOnce());
    rerender({ supplied: second });
    await waitFor(() => expect(result.current.result?.reason).toBe('final'));
    expect(result.current.state).toMatchObject({ runId: 'synthetic-new-run', text: '新运行的公开正文' });
    expect(oldConnect.mock.calls[0][1].aborted).toBe(true);
    await act(async () => {
      old.resolve(
        stream('synthetic-old-run', '不可覆盖新运行的旧正文', 'synthetic-old-run-fact', {
          open: true,
          canceled: () => oldCanceled.resolve(),
        }),
      );
      await oldCanceled.promise;
    });
    expect(result.current.state).toMatchObject({
      runId: 'synthetic-new-run',
      text: '新运行的公开正文',
      complete: true,
    });
    expect(result.current.state.receipts.map(({ fact_id }) => fact_id)).toEqual(['synthetic-new-run-fact']);
    expect(result.current.result?.lastEventId).toBe('4');
    expect(newConnect).toHaveBeenCalledOnce();
  });

  it('unmounts while the reader waits for its next chunk, cancels the body and releases the reader lock', async () => {
    const canceled = deferred<void>(),
      cancel = vi.fn(() => canceled.resolve());
    const response = stream('synthetic-pending-read', '卸载前已显示的正文', 'synthetic-pending-fact', {
      terminal: false,
      open: true,
      canceled: cancel,
    });
    const connect = vi.fn<RecoveryPort['connect']>(async () => response);
    const supplied = port('synthetic-pending-read', connect),
      observed = vi.fn();
    const { result, unmount } = renderHook(() => {
      const view = useRecovery(supplied);
      useEffect(() => {
        observed(view.state);
      }, [view.state]);
      return view;
    });
    await waitFor(() => expect(result.current.state.text).toBe('卸载前已显示的正文'));
    expect(result.current.running).toBe(true);
    expect(response.body!.locked).toBe(true);
    const priorUpdates = observed.mock.calls.length;
    await act(async () => {
      unmount();
      await canceled.promise;
    });
    expect(cancel).toHaveBeenCalledOnce();
    expect(response.body!.locked).toBe(false);
    expect(connect.mock.calls[0][1].aborted).toBe(true);
    expect(connect).toHaveBeenCalledOnce();
    expect(observed).toHaveBeenCalledTimes(priorUpdates);
  });

  it('survives the real StrictMode cleanup and setup cycle without a stale first setup overwriting the second', async () => {
    const run = 'synthetic-strict-mode',
      old = deferred<Response>(),
      oldCanceled = deferred<void>();
    const connect = vi
      .fn<RecoveryPort['connect']>()
      .mockImplementationOnce(() => old.promise)
      .mockResolvedValueOnce(stream(run, '严格模式第二次连接的正文', 'synthetic-strict-new-fact'));
    const supplied = port(run, connect);
    const wrapper = ({ children }: PropsWithChildren) => <StrictMode>{children}</StrictMode>;
    const { result } = renderHook(() => useRecovery(supplied), { wrapper });
    await waitFor(() => expect(result.current.result?.reason).toBe('final'));
    expect(connect).toHaveBeenCalledTimes(2);
    expect(connect.mock.calls[0][1].aborted).toBe(true);
    await act(async () => {
      old.resolve(
        stream(run, '严格模式第一次连接迟到的正文', 'synthetic-strict-old-fact', {
          open: true,
          canceled: () => oldCanceled.resolve(),
        }),
      );
      await oldCanceled.promise;
    });
    expect(result.current.state.text).toBe('严格模式第二次连接的正文');
    expect(result.current.state.receipts.map(({ fact_id }) => fact_id)).toEqual(['synthetic-strict-new-fact']);
    expect(result.current.connection.phase).toBe('closed');
    expect(result.current.running).toBe(false);
  });
});
