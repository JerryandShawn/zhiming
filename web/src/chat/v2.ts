import { chatEvent } from './events';
import { readSse } from './sse';
import { initialStream, object, string, type ChatEvent, type StreamState } from './types';
import { reduceChat } from './reducer';
import { normalizeEnvelope, question, review } from './envelopes';
import { hiddenProfile, publicChatText } from './publicProjection';
import { identifier } from './wireChecksV1';

export type FollowOptions = {
  accept: (event: ChatEvent) => void;
  signal?: AbortSignal;
  headers?: Record<string, string>;
  fetcher?: typeof fetch;
  // Synthetic fixture replay only; never bind a browser's persistent Storage object.
  fixtureStorage?: Storage;
  basePath?: string;
  maxReconnects?: number;
  restore?: (state: StreamState) => void;
};
type FixtureEvent = { id: string; projection: ChatEvent };
const fixtureFormat = 'mingjing-public-fixture-v1';
function isolatedFixture(storage?: Storage) {
  if (
    storage &&
    ((typeof Storage !== 'undefined' && storage instanceof Storage) ||
      Object.prototype.toString.call(storage) === '[object Storage]')
  )
    throw new Error('旧协议回放仅允许独立的合成内存测试存储。');
  return storage;
}
function redact(value: unknown): unknown {
  if (typeof value === 'string') return publicChatText(value);
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === 'object')
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, redact(item)]));
  return value;
}
function questionWire(value: unknown) {
  const source = object(value),
    options = Array.isArray(source.options) ? source.options : [];
  return {
    ...source,
    ask_id: source.askId,
    options: options.map((label, index) =>
      Array.isArray(source.optionIds) ? { id: source.optionIds[index], label } : label,
    ),
  };
}
function reviewWire(value: unknown) {
  const source = object(value);
  return {
    state: source.state,
    reasons: source.reasons,
    ...(typeof source.revisionId === 'string' ? { revision_id: source.revisionId } : {}),
  };
}
/** Decode our marked public fixture format, separately from strict server wire parsing. */
function fixtureEvent(value: unknown): ChatEvent | undefined {
  const source = object(redact(value)),
    type = string(source.type);
  if (type === 'final') {
    const data = object(source.envelope);
    if (typeof data.answer !== 'string' || !Array.isArray(data.receipts) || !Array.isArray(data.decisions)) return;
    const envelope = normalizeEnvelope({
      answer: data.answer,
      professional_appendix: data.professional_appendix,
      memory_receipts: data.receipts,
      decision_options: data.decisions,
      evidence: data.evidence,
      meta: { interrupt: data.interrupt },
    });
    if (!envelope) return;
    const asked = question(questionWire(data.question)),
      checked = review(reviewWire(data.review));
    return {
      type,
      ...(identifier(source.message_id) ? { message_id: source.message_id } : {}),
      envelope: {
        ...envelope,
        ...(data.schema === 'core3.0' || data.schema === 'core4.0' ? { schema: data.schema } : {}),
        ...(typeof data.messageId === 'string' ? { messageId: publicChatText(data.messageId) } : {}),
        ...(asked ? { question: asked } : {}),
        ...(checked ? { review: checked } : {}),
      },
    };
  }
  if (type === 'review') {
    const checked = review(reviewWire(source.review));
    return checked ? { type, review: checked } : undefined;
  }
  const body = Object.fromEntries(Object.entries(source).filter(([key]) => !['v', 'seq', 'ts'].includes(key)));
  if (type === 'memory_receipt') return chatEvent({ ...object(source.receipt), type });
  if (type === 'ask_user') return chatEvent({ ...questionWire(source.question), type });
  const event = chatEvent(body);
  if (!event) return;
  if (event.type === 'started')
    return {
      ...event,
      ...(identifier(source.area_id) ? { area_id: source.area_id } : {}),
      ...(identifier(source.topic_id) ? { topic_id: source.topic_id } : {}),
      ...(typeof source.incognito === 'boolean' ? { incognito: source.incognito } : {}),
    };
  if (event.type === 'status' && ['thinking', 'tool', 'writing', 'reviewing'].includes(string(source.phase)))
    return { ...event, phase: source.phase as 'thinking' | 'tool' | 'writing' | 'reviewing' };
  if ((event.type === 'tool_call' || event.type === 'tool_result') && identifier(source.call_id))
    return { ...event, call_id: source.call_id, ...(typeof source.ok === 'boolean' ? { ok: source.ok } : {}) };
  if (event.type === 'text_reset' && typeof source.revision_id === 'string')
    return { ...event, revision_id: source.revision_id };
  if (event.type === 'present_options')
    return {
      ...event,
      ...(identifier(source.optionsId) ? { optionsId: source.optionsId } : {}),
      ...(typeof source.prompt === 'string' ? { prompt: source.prompt } : {}),
    };
  return event;
}
// Provisional P4 client. Production Chat never invokes this until the server protocol exists.
export async function followV2(runId: string, options: FollowOptions) {
  const {
    accept,
    signal,
    headers = {},
    fetcher = fetch,
    fixtureStorage,
    basePath = '/api/runs',
    maxReconnects = 2,
  } = options;
  const storage = isolatedFixture(fixtureStorage);
  const key = `mingjing-sse-v2:${runId}`;
  let cursor = '',
    snapshot = initialStream();
  const accepted: FixtureEvent[] = [];
  let cacheable = true;
  // Resume a persisted cursor only together with the corresponding projection.
  // Otherwise replay from the beginning so refresh cannot omit earlier text.
  try {
    const cached = object(JSON.parse(storage && options.restore ? storage.getItem(`${key}:events`) || 'null' : 'null'));
    if (storage && options.restore && Object.keys(cached).length) {
      if (cached.format !== fixtureFormat || cached.runId !== runId || !Array.isArray(cached.events))
        throw new Error('合成回放格式无效');
      for (const entry of cached.events) {
        const item = object(entry),
          event = fixtureEvent(item.projection);
        if (object(item.projection).incognito === true) throw new Error('无痕内容不可回放');
        if (!event || !/^\d+$/.test(string(item.id))) throw new Error('合成回放内容无效');
        if (!cursor || BigInt(string(item.id)) > BigInt(cursor)) {
          snapshot = reduceChat(snapshot, event);
          cursor = string(item.id);
          accepted.push({ id: cursor, projection: event });
        }
      }
      options.restore(snapshot);
    }
  } catch {
    cursor = '';
    accepted.length = 0;
    snapshot = initialStream();
    try {
      storage?.removeItem(key);
      storage?.removeItem(`${key}:events`);
    } catch {
      /* Fixture storage may fail. */
    }
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
          snapshot = reduceChat(snapshot, event);
          if (event.type === 'started' && event.incognito) {
            cacheable = false;
            accepted.length = 0;
            try {
              storage?.removeItem(key);
              storage?.removeItem(`${key}:events`);
            } catch {
              /* No new writes follow. */
            }
          }
          if (storage && cacheable) {
            let projection = redact(event) as ChatEvent;
            if (publicChatText(snapshot.text) === hiddenProfile && ['text_delta', 'text_reset'].includes(event.type)) {
              for (const previous of accepted)
                if (['text_delta', 'text_reset'].includes(previous.projection.type))
                  previous.projection = { type: 'text_reset', text: hiddenProfile, reason: 'resumed' };
              projection = { type: 'text_reset', text: hiddenProfile, reason: 'resumed' };
            }
            accepted.push({ id: cursor, projection });
            try {
              storage.setItem(key, cursor);
              storage.setItem(`${key}:events`, JSON.stringify({ format: fixtureFormat, runId, events: accepted }));
            } catch {
              /* The default connection retains its cursor only in memory. */
            }
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
  throw new Error('连接仍未恢复；已展示的内容保留，请手动重试。');
}
