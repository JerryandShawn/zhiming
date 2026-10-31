import { identifier } from '../chat/wireChecksV1';
import type { RunEnvelopeV1 } from '../contracts/runEvents';
import { subscribeLegacyRun } from './followRun';
import { abortable } from '../chat/followV1Async';

export type LegacyBridgeOptions = {
  response: Response;
  body: HTMLElement;
  signal: AbortSignal;
  token: string;
  isCurrent: () => boolean;
  fetcher: typeof fetch;
  onRun: (runId: string) => void;
  onReady: (stop: () => Promise<boolean>) => void;
  onFinal: (envelope: RunEnvelopeV1) => void;
  onRetry: () => void;
};
const states = ['queued', 'running', 'inbox_wait', 'succeeded', 'failed', 'stale', 'cancelled', 'revoked'];

async function readReceipt(response: Response, signal: AbortSignal): Promise<unknown> {
  if (!response.body) throw new Error();
  const reader = response.body.getReader(),
    controller = new AbortController();
  const abort = () => {
    controller.abort();
    void reader.cancel().catch(() => undefined);
  };
  signal.addEventListener('abort', abort, { once: true });
  if (signal.aborted) abort();
  const timer = setTimeout(abort, 45000);
  try {
    const decoder = new TextDecoder();
    let text = '',
      size = 0;
    while (true) {
      const chunk = await abortable(reader.read(), controller.signal);
      if (chunk.done) break;
      size += chunk.value.length;
      if (size > 65536) throw new Error();
      text += decoder.decode(chunk.value, { stream: true });
    }
    return JSON.parse(text + decoder.decode()) as unknown;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', abort);
    void reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

function accepted(value: unknown): { runId: string } | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return;
  const row = value as Record<string, unknown>;
  const fields = ['run_id', 'message_id', 'thread_id', 'status', 'runtime', 'run_url', 'events_url'];
  if (Object.keys(row).length !== fields.length || !fields.every((key) => Object.hasOwn(row, key))) return;
  if (!identifier(row.run_id) || !identifier(row.message_id) || row.runtime !== 'v4') return;
  if (
    typeof row.thread_id !== 'string' ||
    !row.thread_id.trim() ||
    Array.from(row.thread_id).some((letter) => letter.codePointAt(0)! < 0x20 || letter.codePointAt(0) === 0x7f)
  )
    return;
  if (!states.includes(String(row.status))) return;
  const path = `/api/runs/${row.run_id}`;
  if (row.run_url !== path || row.events_url !== `${path}/events`) return;
  return { runId: row.run_id };
}

/** Own only a JSON 202 response. A legacy SSE response stays unread for the old sender. */
export async function followAcceptedLegacyRun(options: LegacyBridgeOptions) {
  if (!/^application\/json(?:\s*;|$)/i.test(options.response.headers.get('Content-Type') ?? '')) return undefined;
  if (options.signal.aborted || !options.isCurrent()) return { reason: 'aborted' as const };
  if (options.response.status !== 202) throw new Error('运行接收回执尚未核对，请保留原来的请求。');
  let value: unknown;
  try {
    value = await readReceipt(options.response, options.signal);
  } catch {
    if (options.signal.aborted || !options.isCurrent()) return { reason: 'aborted' as const };
    throw new Error('运行接收回执尚未核对，请保留原来的请求。');
  }
  const receipt = accepted(value);
  if (!receipt) throw new Error('运行接收回执尚未核对，请保留原来的请求。');
  if (options.signal.aborted || !options.isCurrent()) return { reason: 'aborted' as const };
  const answer = document.createElement('div');
  answer.className = 'answer-reading whitespace-pre-wrap';
  const status = document.createElement('p');
  status.className = 'muted';
  status.setAttribute('role', 'status');
  const review = document.createElement('span');
  review.className = 'muted';
  review.hidden = true;
  const interrupted = document.createElement('span');
  interrupted.className = 'muted';
  interrupted.hidden = true;
  options.body.replaceChildren(answer, review, interrupted, status);
  options.onRun(receipt.runId);
  const subscription = subscribeLegacyRun({
    runId: receipt.runId,
    elements: { answer, status, review, interrupted },
    signal: options.signal,
    isCurrent: options.isCurrent,
    headers: { 'X-Token': options.token },
    fetcher: options.fetcher,
    onFinal(envelope) {
      options.onFinal(envelope);
      if (envelope.review.state === 'revised') {
        const label = document.createElement('span');
        label.className = 'muted';
        label.textContent = '已修订';
        options.body.append(label);
      }
    },
  });
  options.onReady(subscription.stop);
  try {
    const outcome = await subscription.done;
    if (!options.signal.aborted && options.isCurrent() && ['failed', 'error'].includes(outcome.reason)) {
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.className = 'quiet-button';
      retry.textContent = '继续原来这一轮';
      retry.addEventListener('click', () => {
        if (options.isCurrent()) options.onRetry();
      });
      options.body.append(retry);
    }
    return outcome;
  } finally {
    if (options.isCurrent()) options.body.classList.remove('type-caret');
    subscription.dispose();
  }
}
