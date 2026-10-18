import { chatEvent } from './events';
import { readSse } from './sse';
import { initialStream, object, string, type ChatEvent, type StreamState } from './types';
import { reduceChat } from './reducer';

export type FollowOptions = {
  accept: (event: ChatEvent) => void;
  signal?: AbortSignal;
  headers?: Record<string, string>;
  fetcher?: typeof fetch;
  storage?: Storage;
  basePath?: string;
  maxReconnects?: number;
  restore?: (state: StreamState) => void;
};
// Provisional P4 client. Production Chat never invokes this until the server protocol exists.
export async function followV2(runId: string, options: FollowOptions) {
  const {
    accept,
    signal,
    headers = {},
    fetcher = fetch,
    storage = sessionStorage,
    basePath = '/api/runs',
    maxReconnects = 2,
  } = options;
  const key = `mingjing-sse-v2:${runId}`;
  let cursor = '',
    snapshot = initialStream();
  const accepted: { id: string; data: unknown; event: string }[] = [];
  // Resume a persisted cursor only together with the corresponding projection.
  // Otherwise replay from the beginning so refresh cannot omit earlier text.
  try {
    const cached: unknown = JSON.parse(storage.getItem(`${key}:events`) || 'null');
    if (options.restore && Array.isArray(cached)) {
      for (const entry of cached) {
        const item = object(entry),
          event = chatEvent(item.data, string(item.event));
        if (event && /^\d+$/.test(string(item.id)) && (!cursor || BigInt(string(item.id)) > BigInt(cursor))) {
          snapshot = reduceChat(snapshot, event);
          cursor = string(item.id);
          accepted.push({ id: cursor, data: item.data, event: string(item.event) });
        }
      }
      options.restore(snapshot);
    }
  } catch {
    cursor = '';
    accepted.length = 0;
  }
  if (snapshot.complete || snapshot.error) return;
  for (let connection = 0; connection <= maxReconnects; connection++) {
    signal?.throwIfAborted();
    const query = await fetcher(`${basePath}/${encodeURIComponent(runId)}`, { headers, signal });
    if (!query.ok) throw new Error('无法查询运行状态');
    const run = object(await query.json());
    if (run.status === 'succeeded') {
      const event = chatEvent({ type: 'result', result: run.result });
      if (event) accept(event);
      return;
    }
    if (!['running', 'queued'].includes(string(run.status))) throw new Error('运行已停止，请选择继续原来这一轮');
    const response = await fetcher(`${basePath}/${encodeURIComponent(runId)}/events`, {
      signal,
      headers: {
        ...headers,
        Accept: 'text/event-stream',
        ...(cursor ? { 'Last-Event-ID': cursor } : {}),
      },
    });
    if (!response.ok) throw new Error('事件流暂时不可用');
    let terminal = false;
    try {
      await readSse(
        response,
        (frame) => {
          if (frame.data === '[DONE]') return;
          const data: unknown = JSON.parse(frame.data),
            event = chatEvent(data, frame.event);
          if (!event || !/^\d+$/.test(frame.id)) return;
          if (cursor && BigInt(frame.id) <= BigInt(cursor)) return;
          accept(event);
          cursor = frame.id;
          accepted.push({ id: cursor, data, event: frame.event });
          try {
            storage.setItem(key, cursor);
            storage.setItem(`${key}:events`, JSON.stringify(accepted));
          } catch {
            /* This connection still retains its in-memory cursor. */
          }
          if (event.type === 'final' || event.type === 'error') terminal = true;
        },
        signal,
      );
    } catch (error) {
      if (signal?.aborted) throw error;
    }
    if (terminal) return;
  }
  throw new Error('连接仍未恢复；本轮记录和事件游标已保留');
}
