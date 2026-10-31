import { chatEvent } from './events';
import { abortable, cancelUnusedResponse, retryDelay } from './followV1Async';
import { readSse, type Frame } from './sse';
import type { ChatEvent } from './types';
import { identifier } from './wireChecksV1';

export type FollowV1ConnectionState = {
  phase: 'connecting' | 'open' | 'reconnecting' | 'closed' | 'failed' | 'aborted';
  attempt: number;
  lastEventId?: string;
};
export type FollowV1Result = {
  reason: 'final' | 'error' | 'aborted' | 'failed';
  reconnects: number;
  lastEventId?: string;
  code?: 'invalid_config' | 'protocol' | 'sequence_gap' | 'consumer' | 'unavailable';
  error?: string;
};
export type FollowV1Options = {
  connect: (lastEventId: string | undefined, signal: AbortSignal) => Promise<Response>;
  accept: (event: ChatEvent) => unknown;
  onConnectionState?: (state: FollowV1ConnectionState) => void;
  signal: AbortSignal;
  maxReconnects?: number;
  retryMs?: number;
  wait?: (milliseconds: number, signal: AbortSignal) => Promise<void>;
};
class FollowFailure extends Error {
  constructor(
    public code: NonNullable<FollowV1Result['code']>,
    public retryable: boolean,
  ) {
    super(code);
  }
}
class Completed extends Error {
  constructor(public reason: 'final' | 'error') {
    super(reason);
  }
}

function strictEvent(frame: Frame, runId: string): ChatEvent & { seq: number } {
  let value: unknown;
  try {
    value = JSON.parse(frame.data) as unknown;
  } catch {
    throw new FollowFailure('protocol', false);
  }
  const event = chatEvent(value, frame.event);
  if (
    !event ||
    event.v !== 1 ||
    event.run_id !== runId ||
    !Number.isSafeInteger(event.seq) ||
    frame.id !== String(event.seq) ||
    !frame.event
  )
    throw new FollowFailure('protocol', false);
  return event as ChatEvent & { seq: number };
}

/** Strict, memory-only follower. The adapter owns the endpoint and Last-Event-ID header. */
export async function followV1(runId: string, options: FollowV1Options): Promise<FollowV1Result> {
  const { signal } = options;
  const maxReconnects = options.maxReconnects ?? 3,
    retryMs = options.retryMs ?? 500;
  let cursor = 0,
    reconnects = 0;
  const lastEventId = () => (cursor ? String(cursor) : undefined);
  const notify = (phase: FollowV1ConnectionState['phase']) => {
    if (signal.aborted && phase !== 'aborted') return;
    try {
      options.onConnectionState?.({ phase, attempt: reconnects, lastEventId: lastEventId() });
    } catch {
      /* A display observer cannot roll back an accepted event. */
    }
  };
  const finish = (reason: FollowV1Result['reason'], code?: FollowV1Result['code']): FollowV1Result => {
    notify(reason === 'failed' || reason === 'aborted' ? reason : 'closed');
    return {
      reason,
      reconnects,
      lastEventId: lastEventId(),
      ...(code ? { code, error: '连接尚未恢复，已确认的内容保留。' } : {}),
    };
  };
  if (signal.aborted) return finish('aborted');
  if (
    !identifier(runId) ||
    !Number.isSafeInteger(maxReconnects) ||
    maxReconnects < 0 ||
    maxReconnects > 20 ||
    !Number.isSafeInteger(retryMs) ||
    retryMs < 0 ||
    retryMs > 30000
  )
    return finish('failed', 'invalid_config');
  while (!signal.aborted) {
    notify('connecting');
    try {
      signal.throwIfAborted();
      const response = await abortable(options.connect(lastEventId(), signal), signal, cancelUnusedResponse);
      if (signal.aborted) cancelUnusedResponse(response);
      signal.throwIfAborted();
      if (!response.ok || !response.body) {
        cancelUnusedResponse(response);
        throw new FollowFailure('unavailable', ![401, 403].includes(response.status));
      }
      notify('open');
      await readSse(
        response,
        async (frame) => {
          signal.throwIfAborted();
          const event = strictEvent(frame, runId);
          if (event.seq <= cursor) return;
          if (event.seq !== cursor + 1) throw new FollowFailure('sequence_gap', true);
          try {
            await abortable(Promise.resolve(options.accept(event)), signal);
          } catch {
            signal.throwIfAborted();
            throw new FollowFailure('consumer', false);
          }
          signal.throwIfAborted();
          cursor = event.seq;
          if (event.type === 'final' || event.type === 'error') throw new Completed(event.type);
        },
        signal,
      );
      throw new FollowFailure('unavailable', true);
    } catch (reason) {
      if (signal.aborted) return finish('aborted');
      if (reason instanceof Completed) return finish(reason.reason);
      const failure = reason instanceof FollowFailure ? reason : new FollowFailure('unavailable', true);
      if (!failure.retryable || reconnects >= maxReconnects) return finish('failed', failure.code);
      ++reconnects;
      notify('reconnecting');
      try {
        signal.throwIfAborted();
        await abortable((options.wait ?? retryDelay)(retryMs, signal), signal);
      } catch {
        return signal.aborted ? finish('aborted') : finish('failed', 'unavailable');
      }
    }
  }
  return finish('aborted');
}
