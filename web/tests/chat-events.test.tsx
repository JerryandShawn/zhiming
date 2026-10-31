import { describe, expect, it } from 'vitest';
import { chatEvent, envelope } from '../src/chat/events';
import { reduceChat } from '../src/chat/reducer';
import { initialStream } from '../src/chat/types';
import { readSse, type Frame } from '../src/chat/sse';
import { followV2 } from '../src/chat/v2';

function stream(parts: string[]): Response {
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const part of parts) controller.enqueue(new TextEncoder().encode(part));
        controller.close();
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream' } },
  );
}
describe('chat event protocol', () => {
  it('parses CRLF, comment heartbeats, named events and multiline data', async () => {
    const frames: Frame[] = [];
    await readSse(
      stream([': heartbeat\r\n\r', '\nid: 42\r\nevent: text_delta\r\ndata: {\r\ndata: "text":"中文"}\r\n\r\n']),
      (frame) => frames.push(frame),
    );
    expect(frames).toEqual([{ id: '42', event: 'text_delta', data: '{\n"text":"中文"}' }]);
    expect(chatEvent(JSON.parse(frames[0].data), frames[0].event)).toEqual({ type: 'text_delta', text: '中文' });
  });
  it('decodes a multibyte character split across network reads and drops incomplete final frames', async () => {
    const bytes = new TextEncoder().encode('data: {"type":"text_delta","text":"命"}\n\ndata: unfinished');
    const cut = bytes.indexOf(0xe5) + 1;
    const response = new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(bytes.slice(0, cut));
          controller.enqueue(bytes.slice(cut));
          controller.close();
        },
      }),
    );
    const frames: Frame[] = [];
    await readSse(response, (frame) => frames.push(frame));
    expect(frames).toHaveLength(1);
    expect(JSON.parse(frames[0].data).text).toBe('命');
  });
  it('replaces revised text and only displays receipts supplied by program events', () => {
    let state = initialStream();
    const apply = (value: unknown) => {
      const event = chatEvent(value);
      expect(event).toBeDefined();
      state = reduceChat(state, event!);
    };
    apply({ type: 'started', run_id: 'synthetic-run' });
    apply({ type: 'status', text: '正在核对' });
    apply({ type: 'text_delta', text: '我已保存（只是正文）' });
    expect(state.receipts).toEqual([]);
    apply({ type: 'tool_call', name: 'calendar', summary: '核对日期' });
    apply({ type: 'tool_result', name: 'calendar', summary: '已核对' });
    apply({ type: 'text_reset', text: '核对后的回答', reason: 'revised' });
    expect(state.text).toBe('核对后的回答');
    expect(state.revised).toBe(true);
    expect(state.tools[0].done).toBe(true);
    apply({ type: 'memory_receipt', fact_id: 'synthetic-fact', write_status: 'saved', summary: '偏好' });
    apply({ type: 'memory_receipt', fact_id: 'synthetic-fact', write_status: 'stopped' });
    expect(state.receipts).toHaveLength(1);
    expect(state.receipts[0].write_status).toBe('stopped');
    apply({ type: 'ask_user', question: '何时？', options: ['明天'], allow_free_text: true, why: '核对时间' });
    apply({
      type: 'present_options',
      options: [
        { option: '先核对', benefit: '可靠', cost: '等待', risk: '延迟', reversibility: '可调整', first_step: '询问' },
      ],
    });
    apply({ type: 'final', message_id: 'synthetic-message', envelope: { answer: '最终回答' } });
    expect(state.complete).toBe(true);
    expect(state.question?.question).toBe('何时？');
    expect(state.decisions).toHaveLength(1);
    apply({ type: 'error', code: 'OFFLINE', message: '稍后继续', retryable: true });
    expect(state.error).toBe('稍后继续');
  });
  it('does not label resumed text as a reviewer revision or project private fields', () => {
    const state = reduceChat(initialStream(), { type: 'text_reset', text: '恢复', reason: 'resumed' });
    expect(state.revised).toBe(false);
    expect(
      JSON.stringify(envelope({ answer: '公开', private_card_sequence: ['secret'], meta: { birth: 'private' } })),
    ).not.toMatch(/secret|private/);
    expect(chatEvent({ type: 'text_reset', text: '坏帧', reason: 'unknown' })).toBeUndefined();
    expect(chatEvent({ type: 'final' })).toBeUndefined();
  });
  it('queries before reconnecting, sends Last-Event-ID and deduplicates replay', async () => {
    // Synthetic replay uses an isolated fixture store; browser conversation caching is forbidden.
    const values = new Map<string, string>();
    const fixtureStorage = {
      get length() {
        return values.size;
      },
      clear: () => values.clear(),
      key: (index: number) => [...values.keys()][index] ?? null,
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      },
      removeItem: (key: string) => {
        values.delete(key);
      },
    };
    let connections = 0;
    const seenHeaders: Headers[] = [],
      events: unknown[] = [];
    const fetcher: typeof fetch = async (input, init) => {
      if (!String(input).endsWith('/events')) return Response.json({ status: 'running' });
      seenHeaders.push(new Headers(init?.headers));
      connections++;
      return connections === 1
        ? stream(['id: 1\ndata: {"type":"text_delta","text":"甲"}\n\n'])
        : stream([
            'id: 1\ndata: {"type":"text_delta","text":"甲"}\n\nid: 2\ndata: {"type":"text_reset","text":"乙","reason":"revised"}\n\nid: 3\ndata: {"type":"final","envelope":{"answer":"乙"}}\n\n',
          ]);
    };
    await followV2('synthetic-run', { fetcher, fixtureStorage, accept: (event) => events.push(event) });
    expect(seenHeaders[0].get('Last-Event-ID')).toBeNull();
    expect(seenHeaders[1].get('Last-Event-ID')).toBe('1');
    expect(events).toHaveLength(3);
    expect(fixtureStorage.getItem('mingjing-sse-v2:synthetic-run')).toBe('3');
  });
  it('restores the text projection together with a saved cursor after refresh', async () => {
    const values = new Map<string, string>();
    const fixtureStorage = {
      get length() {
        return values.size;
      },
      clear: () => values.clear(),
      key: (index: number) => [...values.keys()][index] ?? null,
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      },
      removeItem: (key: string) => {
        values.delete(key);
      },
    };
    fixtureStorage.setItem(
      'mingjing-sse-v2:restored:events',
      JSON.stringify({
        format: 'mingjing-public-fixture-v1',
        runId: 'restored',
        events: [
          { id: '1', projection: { type: 'text_delta', text: '先前正文' } },
          {
            id: '4',
            projection: {
              type: 'memory_receipt',
              receipt: { fact_id: 'synthetic', write_status: 'saved', summary: '' },
            },
          },
        ],
      }),
    );
    let state = initialStream();
    const headers: Headers[] = [];
    const fetcher: typeof fetch = async (input, init) => {
      if (!String(input).endsWith('/events')) return Response.json({ status: 'running' });
      headers.push(new Headers(init?.headers));
      return stream([
        'id: 5\ndata: {"type":"text_delta","text":"与新正文"}\n\nid: 6\ndata: {"type":"final","envelope":{"answer":"先前正文与新正文"}}\n\n',
      ]);
    };
    await followV2('restored', {
      fetcher,
      fixtureStorage,
      restore: (restored) => {
        state = restored;
      },
      accept: (event) => {
        state = reduceChat(state, event);
      },
    });
    expect(headers[0].get('Last-Event-ID')).toBe('4');
    expect(state.text).toBe('先前正文与新正文');
    expect(state.receipts).toHaveLength(1);
  });
});
