import { abortable, cancelUnusedResponse, retryDelay } from '../chat/followV1Async';
import { readSse } from '../chat/sse';
import { parseRunEventV1, type RunEnvelopeV1 } from '../contracts/runEvents';
import { createLegacyRunView, type LegacyRunElements } from './runView';

export type LegacyRunOptions = {
  runId: string;
  elements: LegacyRunElements;
  fetcher: typeof fetch;
  headers: HeadersInit;
  signal: AbortSignal;
  isCurrent: () => boolean;
  onFinal?: (envelope: RunEnvelopeV1) => void;
};
export type LegacyRunFinish = { reason: 'final' | 'cancelled' | 'error' | 'failed' | 'aborted'; lastEventId?: string };
class Complete extends Error {
  constructor(public reason: LegacyRunFinish['reason']) {
    super(reason);
  }
}
class Failure extends Error {
  constructor(public retryable: boolean) {
    super('本轮连接尚未恢复，已显示的内容保留。');
  }
}

/** Explicit opt-in only. Reconnects GET; never replays the original message POST. */
export function subscribeLegacyRun(options: LegacyRunOptions) {
  const view = createLegacyRunView(options);
  const lifetime = new AbortController();
  const headers = new Headers(options.headers);
  const endpoint = `/api/runs/${encodeURIComponent(options.runId)}`;
  const parentAbort = () => lifetime.abort();
  options.signal.addEventListener('abort', parentAbort, { once: true });
  if (options.signal.aborted) lifetime.abort();
  let settled = false,
    stopping = false;
  function current() {
    if (!options.isCurrent()) lifetime.abort();
    lifetime.signal.throwIfAborted();
  }
  function result(reason: LegacyRunFinish['reason']): LegacyRunFinish {
    return { reason, lastEventId: view.snapshot().lastEventId };
  }
  async function connection() {
    const channel = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const resetIdle = () => {
      clearTimeout(timer);
      timer = setTimeout(() => channel.abort(), 45000);
    };
    const abort = () => channel.abort();
    lifetime.signal.addEventListener('abort', abort, { once: true });
    resetIdle();
    let response: Response | undefined;
    try {
      current();
      const requestHeaders = new Headers(headers);
      requestHeaders.set('Accept', 'text/event-stream');
      requestHeaders.delete('Last-Event-ID');
      const cursor = view.snapshot().lastEventId;
      if (cursor) requestHeaders.set('Last-Event-ID', cursor);
      response = await abortable(
        options.fetcher(`${endpoint}/events`, {
          method: 'GET',
          headers: requestHeaders,
          signal: channel.signal,
          credentials: 'same-origin',
          cache: 'no-store',
          redirect: 'error',
        }),
        channel.signal,
        cancelUnusedResponse,
      );
      current();
      if (!response.ok) throw new Failure(response.status >= 500);
      if (!/^text\/event-stream(?:\s*;|$)/i.test(response.headers.get('Content-Type') ?? '') || !response.body)
        throw new Failure(false);
      await readSse(
        response,
        (frame) => {
          current();
          let value: unknown;
          try {
            value = JSON.parse(frame.data) as unknown;
          } catch {
            throw new Failure(false);
          }
          const event = parseRunEventV1(value, frame.event);
          if (!event || frame.id !== String(event.seq)) throw new Failure(false);
          const applied = view.accept(value, frame.event);
          if (applied === 'stale') {
            current();
            throw new Complete('aborted');
          }
          if (applied === 'gap') throw new Failure(true);
          if (applied !== 'applied' && applied !== 'duplicate') throw new Failure(false);
          resetIdle();
          if (applied === 'duplicate') return;
          if (event.type === 'final') {
            try {
              options.onFinal?.(event.envelope);
            } catch {
              throw new Failure(false);
            }
            throw new Complete('final');
          }
          if (event.type === 'error') throw new Complete(event.code === 'RUN_CANCELLED' ? 'cancelled' : 'error');
        },
        channel.signal,
        resetIdle,
      );
      throw new Failure(true);
    } finally {
      clearTimeout(timer!);
      lifetime.signal.removeEventListener('abort', abort);
      channel.abort();
      if (response) cancelUnusedResponse(response);
    }
  }
  async function follow(): Promise<LegacyRunFinish> {
    try {
      for (let attempt = 0; attempt <= 3; attempt++) {
        try {
          current();
          await connection();
        } catch (error) {
          if (lifetime.signal.aborted) return result('aborted');
          if (error instanceof Complete) return result(error.reason);
          if (error instanceof Failure && !error.retryable) break;
          if (attempt === 3) break;
          current();
          options.elements.status.textContent = '连接波动，正在接着显示…';
          await retryDelay(500, lifetime.signal);
        }
      }
      current();
      options.elements.status.textContent = '连接尚未恢复，已显示的内容保留。';
      return result('failed');
    } catch {
      return result('aborted');
    } finally {
      settled = true;
      lifetime.abort();
      options.signal.removeEventListener('abort', parentAbort);
    }
  }
  return {
    done: follow(),
    snapshot: view.snapshot,
    async stop(): Promise<boolean> {
      if (settled || stopping || !options.isCurrent() || lifetime.signal.aborted) return false;
      stopping = true;
      options.elements.status.textContent = '正在停止…';
      const cancel = new AbortController();
      const timer = setTimeout(() => cancel.abort(), 2000);
      const abort = () => cancel.abort();
      lifetime.signal.addEventListener('abort', abort, { once: true });
      let response: Response | undefined;
      try {
        const requestHeaders = new Headers(headers);
        requestHeaders.set('Content-Type', 'application/json');
        response = await abortable(
          options.fetcher(`${endpoint}/cancel`, {
            method: 'POST',
            headers: requestHeaders,
            body: '{}',
            signal: cancel.signal,
            credentials: 'same-origin',
            cache: 'no-store',
            redirect: 'error',
          }),
          cancel.signal,
          cancelUnusedResponse,
        );
        current();
        if (!response.ok) throw new Failure(false);
        // HTTP ack is not authority to mark partial text as cancelled.
        return true;
      } catch {
        if (!settled && !lifetime.signal.aborted && options.isCurrent())
          options.elements.status.textContent = '停止尚未确认，已显示的内容保留。';
        return false;
      } finally {
        clearTimeout(timer);
        lifetime.signal.removeEventListener('abort', abort);
        if (response) cancelUnusedResponse(response);
        stopping = false;
      }
    },
    dispose() {
      view.dispose();
      lifetime.abort();
    },
  };
}
