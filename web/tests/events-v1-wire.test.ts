import { describe, expect, it, vi } from 'vitest';
import { parseWireEventV1, isWireTimestampV1 } from '../src/chat/wireV1';
import { chatEvent } from '../src/chat/events';
import { readSse, type Frame } from '../src/chat/sse';
import { hiddenProfile } from '../src/chat/publicProjection';

const common = { v: 1, run_id: 'synthetic-run', seq: 1, ts: '2026-10-21T01:02:03+08:00' };
const ask = {
  ask_id: 'ask-1',
  question: '先看哪一项？',
  options: [
    { id: 'a', label: '安排' },
    { id: 'b', label: '准备' },
  ],
  allow_free_text: true,
  multi: true,
  why: '先从你在意的开始。',
};
const option = {
  id: 'option-1',
  title: '先了解',
  benefit: '补齐信息',
  cost: '',
  risk: '',
  reversibility: 'unknown',
  first_step: '写出问题',
  unknowns: ['cost', 'risk', 'reversibility'],
};
const options = {
  options_id: 'options-1',
  prompt: '可以从这两条路开始',
  options: [option, { ...option, id: 'option-2' }],
};
const memory = { fact_id: 'fact-1', write_status: 'saved', summary: '合成偏好', sensitive: false };
const review = { state: 'revised', reasons: [{ code: 'generic_barnum', severity: 3 }], revision_id: 'revision-1' };
const envelope = {
  schema: 'core4.0',
  message_id: 'message-1',
  text: '核对后的内容',
  receipts: [memory],
  used_fact_ids: [],
  used_claim_ids: [],
  asked: ask,
  options,
  review,
  usage: {},
};
const bodies = {
  started: {
    thread_id: 'thread-1',
    message_id: 'message-1',
    area_id: 'career',
    topic_id: 'interview',
    incognito: false,
  },
  status: { text: '正在核对', phase: 'reviewing' },
  tool_call: { call_id: 'call-1', name: 'memory_search', summary: '查找相关记忆' },
  tool_result: { call_id: 'call-1', name: 'memory_search', ok: true, summary: '已核对', receipt: memory },
  text_delta: { text: '一些内容' },
  text_reset: { text: '恢复的完整内容', reason: 'resumed', revision_id: 'revision-1' },
  memory_receipt: memory,
  ask_user: ask,
  present_options: options,
  review,
  final: { message_id: 'message-1', envelope },
  error: { code: 'OFFLINE', message: '网络暂时波动，请稍后继续。', retryable: true },
};

describe('frozen event contract v1', () => {
  it.each(Object.entries(bodies))('accepts the documented %s shape and retains common identity', (type, body) => {
    const value = { ...common, ...body };
    expect(parseWireEventV1(value, type)).toEqual({ ...value, type });
    expect(chatEvent(value, type)).toMatchObject({ type, ...common });
  });

  it.each(['v', 'run_id', 'seq', 'ts'])('rejects a missing common %s without falling back to legacy', (key) => {
    const value: Record<string, unknown> = { ...common, ...bodies.status };
    delete value[key];
    if (key !== 'v') expect(chatEvent(value, 'status')).toBeUndefined();
    expect(parseWireEventV1(value, 'status')).toBeUndefined();
  });

  it.each([2, '1', null, false])('rejects unsupported explicit version %s', (v) => {
    expect(chatEvent({ ...common, v, ...bodies.status }, 'status')).toBeUndefined();
  });

  it.each([-1, 0.5, Number.MAX_SAFE_INTEGER + 1, '2'])('rejects invalid sequence %s', (seq) => {
    expect(chatEvent({ ...common, seq, ...bodies.text_delta }, 'text_delta')).toBeUndefined();
  });

  it.each([
    '2026-10-21T01:02:03Z',
    '2026-10-21T01:02:03+09:00',
    '2026-02-29T01:02:03+08:00',
    '2026-10-32T01:02:03+08:00',
    '2026-10-21T24:02:03+08:00',
  ])('rejects an offset or calendar mismatch %s independently of host timezone', (ts) => {
    expect(isWireTimestampV1(ts)).toBe(false);
    expect(chatEvent({ ...common, ts, ...bodies.status }, 'status')).toBeUndefined();
  });

  it('accepts a leap date and fractional seconds with the frozen offset', () => {
    expect(isWireTimestampV1('2028-02-29T00:00:00.123456+08:00')).toBe(true);
  });

  it('rejects event-name mismatches, unknown types and temporary payload extensions', () => {
    expect(chatEvent({ ...common, type: 'text_delta', text: '内容' }, 'final')).toBeUndefined();
    expect(chatEvent({ ...common }, 'heartbeat')).toBeUndefined();
    expect(chatEvent({ ...common, ...bodies.status, reviewPending: true }, 'status')).toBeUndefined();
    expect(chatEvent({ ...common, text: '内容' }, 'status')).toBeUndefined();
  });

  it.each(['saved', 'pending_confirm', 'undone', 'rejected'])(
    'accepts exactly the memory status %s',
    (write_status) => {
      expect(chatEvent({ ...common, ...memory, write_status }, 'memory_receipt')).toMatchObject({
        receipt: { write_status, sensitive: false },
      });
    },
  );

  it('rejects legacy receipt statuses and missing sensitivity only in explicit v1', () => {
    expect(chatEvent({ ...common, ...memory, write_status: 'stopped' }, 'memory_receipt')).toBeUndefined();
    const noSensitivity: Record<string, unknown> = { ...common, ...memory };
    delete noSensitivity.sensitive;
    expect(chatEvent(noSensitivity, 'memory_receipt')).toBeUndefined();
    expect(chatEvent({ type: 'memory_receipt', fact_id: 'legacy', write_status: 'stopped' })).toBeDefined();
  });

  it('retains stable question and decision IDs and unknown fields in their public projection', () => {
    expect(chatEvent({ ...common, ...ask }, 'ask_user')).toMatchObject({
      question: { askId: 'ask-1', optionIds: ['a', 'b'], options: ['安排', '准备'], multi: true },
    });
    expect(chatEvent({ ...common, ...options }, 'present_options')).toMatchObject({
      optionsId: 'options-1',
      prompt: options.prompt,
      options: [{ id: 'option-1', option: '先了解', unknowns: option.unknowns }, { id: 'option-2' }],
    });
  });

  it('rejects duplicate option IDs and decision counts or reversibility outside the frozen contract', () => {
    expect(chatEvent({ ...common, ...ask, options: [ask.options[0], ask.options[0]] }, 'ask_user')).toBeUndefined();
    for (const values of [
      [option],
      [option, option],
      Array.from({ length: 5 }, (_, index) => ({ ...option, id: `${index}` })),
    ])
      expect(chatEvent({ ...common, ...options, options: values }, 'present_options')).toBeUndefined();
    expect(
      chatEvent(
        { ...common, ...options, options: [{ ...option, reversibility: '随时可停' }, options.options[1]] },
        'present_options',
      ),
    ).toBeUndefined();
  });

  it('rejects invalid reviewer severity and incomplete or mismatched final envelopes', () => {
    expect(
      chatEvent({ ...common, ...review, reasons: [{ code: 'generic_barnum', severity: 6 }] }, 'review'),
    ).toBeUndefined();
    expect(chatEvent({ ...common, message_id: 'other-message', envelope }, 'final')).toBeUndefined();
    expect(
      chatEvent({ ...common, message_id: 'message-1', envelope: { schema: 'core4.0', text: '不完整' } }, 'final'),
    ).toBeUndefined();
  });

  it('continues to redact birth data in status, receipt summaries and dedicated tool receipts', () => {
    const summary = 'birth.date: 1990-01-01';
    expect(chatEvent({ ...common, ...bodies.status, text: summary }, 'status')).toMatchObject({ text: hiddenProfile });
    expect(chatEvent({ ...common, ...memory, summary }, 'memory_receipt')).toMatchObject({
      receipt: { summary: hiddenProfile },
    });
    expect(
      chatEvent(
        { ...common, ...bodies.tool_result, receipt: { kind: 'profile', field: 'birth', ...memory } },
        'tool_result',
      ),
    ).toMatchObject({ receipt: undefined });
    expect(chatEvent({ ...common, ...bodies.started, thread_id: summary }, 'started')).toBeUndefined();
  });

  it('treats split ping comments as liveness only, without frames or sequence consumption', async () => {
    const heartbeat = vi.fn(),
      frames: Frame[] = [];
    const chunks = [
      'id: 4\nevent: text_delta\ndata: {"text":"甲"}\n\n: pi',
      'ng\r\n\r\nid: 5\nevent: text_delta\ndata: {"text":"乙"}\n\n',
    ];
    const response = new Response(
      new ReadableStream({
        start(controller) {
          for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk));
          controller.close();
        },
      }),
    );
    await readSse(response, (frame) => frames.push(frame), undefined, heartbeat);
    expect(heartbeat).toHaveBeenCalledTimes(1);
    expect(frames.map((frame) => frame.id)).toEqual(['4', '5']);
  });
});
