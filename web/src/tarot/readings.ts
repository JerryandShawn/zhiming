import { api, ApiError, authHeaders, operationNamespace, requireLogin } from '../api/client';
import { readSse } from '../chat/sse';
import { path } from './draws';
import { list, object, reading, text, type Reading } from './public';

type Attempt = {
  request_id: string;
  supplement: string;
  reading_id?: string;
  run_id?: string;
  cancel_requested?: boolean;
};
export class ReadingStopped extends Error {}
const key = (drawId: string, namespace = operationNamespace()) => `mingjing:tarot:reading:${namespace}:${drawId}`;
export function pendingReading(drawId: string): Attempt | undefined {
  try {
    const value = object(JSON.parse(sessionStorage.getItem(key(drawId)) || 'null'));
    return text(value.request_id)
      ? {
          request_id: text(value.request_id),
          supplement: text(value.supplement),
          ...(text(value.reading_id) ? { reading_id: text(value.reading_id) } : {}),
          ...(text(value.run_id) ? { run_id: text(value.run_id) } : {}),
          ...(value.cancel_requested === true ? { cancel_requested: true } : {}),
        }
      : undefined;
  } catch {
    return undefined;
  }
}
export function clearReading(drawId: string, namespace = operationNamespace()) {
  sessionStorage.removeItem(key(drawId, namespace));
}
export function markReadingStop(drawId: string, requested: boolean) {
  const pending = pendingReading(drawId);
  if (pending) sessionStorage.setItem(key(drawId), JSON.stringify({ ...pending, cancel_requested: requested }));
}
function attempt(drawId: string, supplement: string): Attempt {
  const pending = pendingReading(drawId);
  if (pending && pending.supplement !== supplement) throw new Error('原解读尚未确认，请先重试原请求；补充内容已保留。');
  const value = pending ?? { request_id: crypto.randomUUID(), supplement };
  sessionStorage.setItem(key(drawId), JSON.stringify(value));
  return value;
}
export async function loadReadings(drawId: string): Promise<Reading[]> {
  return list(await api<unknown>(`${path(drawId)}/readings`)).map(reading);
}
async function postStream(url: string, payload: Record<string, unknown>, signal: AbortSignal): Promise<Response> {
  const namespace = operationNamespace();
  const response = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    signal,
    headers: { ...authHeaders(), 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(payload),
  });
  if (namespace !== operationNamespace()) throw new DOMException('会话已切换', 'AbortError');
  if (response.status === 401) requireLogin();
  if (!response.ok) throw new Error(`解读请求未确认（${response.status}），牌阵保持不变。`);
  return response;
}
/** Retry the existing durable run; this function never calls a draw endpoint. */
export async function requestReading(
  drawId: string,
  supplement: string,
  signal: AbortSignal,
  update: (status: string, runId?: string) => void,
): Promise<Reading[]> {
  const namespace = operationNamespace();
  const storageKey = key(drawId, namespace);
  function assertCurrent() {
    signal.throwIfAborted();
    if (namespace !== operationNamespace()) throw new DOMException('会话已切换', 'AbortError');
  }
  const pending = attempt(drawId, supplement);
  let run: Record<string, unknown> = {};
  try {
    run = object(await api<unknown>(`/api/runs/${encodeURIComponent(`reading:${pending.request_id}`)}`));
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 404) throw error;
  }
  assertCurrent();
  if (run.status === 'succeeded') {
    const versions = await loadReadings(drawId);
    assertCurrent();
    if (
      !pending.reading_id ||
      !versions.some((v) => v.id === pending.reading_id && v.status === 'success' && v.answer)
    ) {
      // A response may have been lost before started; recover through the same request's replay stream.
      update('原解读已完成，正在确认保存回执…', text(run.id));
    } else {
      clearReading(drawId, namespace);
      return versions;
    }
  }
  if (run.status === 'cancelled') throw new ReadingStopped('这次解读已停止，固定牌阵仍保留。请明确开始另一版解读。');
  const runId = text(run.id);
  if (runId) update('正在恢复原解读…', runId);
  const retry = run.status === 'failed' || run.status === 'stale';
  const response = await postStream(
    retry ? `/api/runs/${encodeURIComponent(runId)}/retry` : `${path(drawId)}/readings`,
    retry
      ? { request_id: `retry:${pending.request_id}` }
      : { request_id: pending.request_id, supplement: pending.supplement },
    signal,
  );
  assertCurrent();
  let received = false,
    failed = false;
  await readSse(
    response,
    (frame) => {
      assertCurrent();
      if (frame.data === '[DONE]') return;
      let event: Record<string, unknown>;
      try {
        event = object(JSON.parse(frame.data));
      } catch {
        throw new Error('解读事件不完整，请恢复原解读。');
      }
      if (event.type === 'started') {
        pending.reading_id = text(event.reading_id) || pending.reading_id;
        pending.run_id = text(event.run_id) || pending.run_id;
        sessionStorage.setItem(storageKey, JSON.stringify(pending));
        update('正在解读这次固定牌阵…', text(event.run_id));
      }
      if (event.type === 'status') update('正在核对本轮资料与依据…');
      if (event.type === 'result') received = true;
      if (event.type === 'error') failed = true;
    },
    signal,
  );
  if (failed || !received) throw new Error('解释未完成。牌阵已保留，可刷新记录或重试原解读。');
  const versions = await loadReadings(drawId);
  assertCurrent();
  if (!pending.reading_id || !versions.some((v) => v.id === pending.reading_id && v.status === 'success' && v.answer))
    throw new Error('解读保存尚未确认，请稍后刷新记录。');
  clearReading(drawId, namespace);
  return versions;
}
