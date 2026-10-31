import { abortable, cancelUnusedResponse, retryDelay } from '../chat/followV1Async';
import { readSse } from '../chat/sse';
import { parseRunEventV1, type RunEventV1 } from '../contracts/runEvents';
import { threadAcceptance, type ThreadAcceptance } from './contracts';
import type { SubmissionOwner } from './submit';

export type ThreadFollowResult = {
  reason: 'final' | 'error' | 'aborted' | 'failed' | 'needs_state';
  reconnects: number;
  lastEventId?: string;
  code?:
    'invalid_config' | 'protocol' | 'consumer' | 'unavailable' | 'unauthorized' | 'forbidden' | 'cursor_unavailable';
};
export type ThreadFollowOptions = SubmissionOwner & {
  fetcher: typeof fetch;
  // This owner must keep the whole projection with this in-memory cursor.
  accept: (event: RunEventV1, signal: AbortSignal) => unknown;
  onConnection?: (phase: 'connecting' | 'open' | 'reconnecting') => void;
  maxReconnects?: number;
  retryMs?: number;
  wait?: (milliseconds: number, signal: AbortSignal) => Promise<void>;
};
class Failure extends Error {
  constructor(
    public code: NonNullable<ThreadFollowResult['code']>,
    public retryable = false,
  ) {
    super(code);
  }
}
class Complete extends Error {
  constructor(public reason: 'final' | 'error') {
    super(reason);
  }
}

/** P3-specific increasing sequence policy; the original demo's contiguous follower stays unchanged.
 * Only consume a fresh execution here. Epoch/retry restoration needs authoritative state first.
 * A 422 ends this subscription with needs_state; never retry or clear that cursor automatically.
 */
export async function followThreadEvents(
  receipt: ThreadAcceptance,
  options: ThreadFollowOptions,
): Promise<ThreadFollowResult> {
  const lifetime = new AbortController();
  const abort = () => lifetime.abort();
  const maxReconnects = options.maxReconnects ?? 3,
    retryMs = options.retryMs ?? 500;
  let cursor = 0,
    reconnects = 0;
  const result = (reason: ThreadFollowResult['reason'], code?: ThreadFollowResult['code']): ThreadFollowResult => ({
    reason,
    reconnects,
    ...(cursor ? { lastEventId: String(cursor) } : {}),
    ...(code ? { code } : {}),
  });
  const current = () => {
    if (options.signal.aborted || !options.isCurrent()) lifetime.abort();
    lifetime.signal.throwIfAborted();
  };
  const notify = (phase: 'connecting' | 'open' | 'reconnecting') => {
    current();
    try {
      options.onConnection?.(phase);
    } catch {
      /* A display observer cannot undo a consumed event. */
    }
    current();
  };
  let accepted: ThreadAcceptance;
  try {
    accepted = threadAcceptance(receipt);
    if (
      accepted.runtime !== 'v4' ||
      !Number.isSafeInteger(maxReconnects) ||
      maxReconnects < 0 ||
      maxReconnects > 20 ||
      !Number.isSafeInteger(retryMs) ||
      retryMs < 0 ||
      retryMs > 30000
    )
      return result('failed', 'invalid_config');
  } catch {
    return result('failed', 'invalid_config');
  }
  if (accepted.runtime !== 'v4') return result('failed', 'invalid_config');
  if (!['queued', 'running', 'inbox_wait'].includes(accepted.status)) return result('needs_state');
  const endpoint = accepted.events_url;
  options.signal.addEventListener('abort', abort, { once: true });

  async function connection() {
    const channel = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const resetIdle = () => {
      clearTimeout(timer);
      timer = setTimeout(() => channel.abort(), 45000);
    };
    const abortChannel = () => channel.abort();
    lifetime.signal.addEventListener('abort', abortChannel, { once: true });
    let response: Response | undefined;
    resetIdle();
    try {
      current();
      const headers = new Headers(options.headers());
      current();
      headers.set('Accept', 'text/event-stream');
      headers.delete('Last-Event-ID');
      if (cursor) headers.set('Last-Event-ID', String(cursor));
      response = await abortable(
        options.fetcher(endpoint, {
          method: 'GET',
          headers,
          signal: channel.signal,
          credentials: 'same-origin',
          cache: 'no-store',
          redirect: 'error',
        }),
        channel.signal,
        cancelUnusedResponse,
      );
      current();
      if (response.status === 422) throw new Failure('cursor_unavailable');
      if (response.status === 401) throw new Failure('unauthorized');
      if (response.status === 403) throw new Failure('forbidden');
      if (response.status !== 200) throw new Failure('unavailable', response.status >= 500);
      if (!response.body || !/^text\/event-stream(?:\s*;|$)/i.test(response.headers.get('Content-Type') ?? ''))
        throw new Failure('protocol');
      notify('open');
      await readSse(
        response,
        async (frame) => {
          current();
          let raw: unknown;
          try {
            raw = JSON.parse(frame.data) as unknown;
          } catch {
            throw new Failure('protocol');
          }
          const event = parseRunEventV1(raw, frame.event);
          if (!event || event.run_id !== accepted.run_id || frame.id !== String(event.seq) || !frame.event)
            throw new Failure('protocol');
          resetIdle();
          if (event.seq <= cursor) return;
          try {
            await abortable(Promise.resolve(options.accept(event, channel.signal)), channel.signal);
          } catch {
            current();
            throw new Failure('consumer');
          }
          current();
          channel.signal.throwIfAborted();
          cursor = event.seq;
          if (event.type === 'final' || event.type === 'error') throw new Complete(event.type);
        },
        channel.signal,
        () => {
          current();
          resetIdle();
        },
      );
      throw new Failure('unavailable', true);
    } finally {
      clearTimeout(timer!);
      lifetime.signal.removeEventListener('abort', abortChannel);
      if (response) cancelUnusedResponse(response);
    }
  }

  try {
    while (true) {
      try {
        notify('connecting');
        await connection();
      } catch (error) {
        if (lifetime.signal.aborted) return result('aborted');
        if (error instanceof Complete) return result(error.reason);
        const failure = error instanceof Failure ? error : new Failure('unavailable', true);
        if (failure.code === 'cursor_unavailable') return result('needs_state', failure.code);
        if (!failure.retryable || reconnects >= maxReconnects) return result('failed', failure.code);
        reconnects++;
        notify('reconnecting');
        await abortable((options.wait ?? retryDelay)(retryMs, lifetime.signal), lifetime.signal);
      }
    }
  } catch {
    return result(lifetime.signal.aborted ? 'aborted' : 'failed', lifetime.signal.aborted ? undefined : 'unavailable');
  } finally {
    options.signal.removeEventListener('abort', abort);
  }
}
