import { normalizeEnvelope } from '../chat/events';
import { reduceChat } from '../chat/reducer';
import { initialStream, type StreamState } from '../chat/types';
import type { RunEnvelopeV1 } from '../contracts/runEvents';
import { ThreadRequestError } from './contracts';
import type { ThreadRunState } from './authority';

export type ThreadView = Readonly<{
  phase: 'idle' | 'checking' | 'following' | 'needs_check' | 'complete' | 'interrupted' | 'ended' | 'detached';
  stream: StreamState;
  stopping: boolean;
  notice: string;
  server?: ThreadRunState;
  lastEventId?: string;
}>;
export const detachedView = (): ThreadView =>
  Object.freeze({ phase: 'detached', stream: initialStream(), stopping: false, notice: '' });
export const activeRun = (state: ThreadRunState) => ['queued', 'running', 'inbox_wait'].includes(state.status);

export function authoritativeProjection(view: ThreadView, state: ThreadRunState): ThreadView {
  if (activeRun(state)) {
    if (['complete', 'interrupted', 'ended'].includes(view.phase) || state.attempts > 1)
      return {
        ...view,
        server: state,
        phase: 'needs_check',
        stopping: false,
        notice: '本轮执行已切换，旧内容尚未重新核对。',
        stream: {
          ...initialStream(),
          runId: view.stream.runId,
          threadId: view.stream.threadId,
          incognito: view.stream.incognito,
          text: view.stream.text,
        },
      };
    return { ...view, server: state };
  }
  if (state.status === 'succeeded' && state.final) {
    const envelope = normalizeEnvelope(state.final);
    if (!envelope || envelope.schema !== 'core4.0') throw new ThreadRequestError('receipt');
    // A final with null cards/empty receipts must not inherit abandoned stream cards or saved claims.
    const base = {
      ...view.stream,
      receipts: [],
      question: undefined,
      decisions: [],
      optionsId: undefined,
      optionsPrompt: undefined,
      answered: undefined,
      revised: false,
      revisionId: undefined,
    };
    return {
      ...view,
      server: state,
      phase: 'complete',
      stopping: false,
      notice: '',
      stream: reduceChat(base, { type: 'final', envelope, message_id: state.final.message_id }),
    };
  }
  const cancelled = state.status === 'cancelled',
    revoked = state.status === 'revoked';
  const code = cancelled
    ? 'RUN_CANCELLED'
    : revoked
      ? 'SOURCE_REVOKED'
      : state.status === 'stale'
        ? 'RUN_STALE'
        : 'RUN_FAILED';
  const message = cancelled
    ? '本轮已停止，已出的内容保留。'
    : revoked
      ? '本轮采用的资料已撤销。'
      : '本轮尚未完成，请核对原来的请求。';
  const base = revoked ? { ...initialStream(), runId: view.stream.runId, threadId: view.stream.threadId } : view.stream;
  return {
    ...view,
    server: state,
    phase: cancelled ? 'interrupted' : 'ended',
    stopping: false,
    notice: message,
    stream: reduceChat(base, { type: 'error', code, message, retryable: !cancelled && !revoked }),
  };
}

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object')
    return Object.fromEntries(
      Object.entries(value)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, item]) => [key, canonical(item)]),
    );
  return value;
}
/** GET adds legacy answer; it is not a second authority for core4 text. Object key order is immaterial. */
export function sameFinal(left: RunEnvelopeV1, right: RunEnvelopeV1) {
  const core = (value: RunEnvelopeV1) => Object.fromEntries(Object.entries(value).filter(([key]) => key !== 'answer'));
  return JSON.stringify(canonical(core(left))) === JSON.stringify(canonical(core(right)));
}
