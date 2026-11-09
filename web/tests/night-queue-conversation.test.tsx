import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatEvent } from '../src/chat/types';
import { playDemo, type DemoScenario } from '../src/night/events';
import { createNightPort } from '../src/night/port';
import { createInputQueue, createMockQueuePort, type QueueCommand } from '../src/night/queue';
import { useNormalConversation } from '../src/night/useNormalConversation';
import { INITIAL_DEMO_PROMPT } from '../src/night/conversationTypes';

vi.mock('../src/night/events', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/night/events')>();
  return { ...actual, playDemo: vi.fn() };
});

function deferred() {
  let resolve!: () => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<void>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}
type StreamGate = {
  scenario: DemoScenario;
  runId: string;
  signal: AbortSignal;
  emit: (event: ChatEvent) => void;
  finish: () => void;
};
let streams: StreamGate[];
const originalImages = ['data:image/png;base64,c3ludGhldGljLWE='];
const nextImages = ['data:image/png;base64,c3ludGhldGljLWI='];
beforeEach(() => {
  streams = [];
  vi.mocked(playDemo).mockImplementation(async (scenario, emit, signal, _delay, context) => {
    const gate = deferred();
    signal.addEventListener('abort', () => gate.reject(new DOMException('Stopped', 'AbortError')), { once: true });
    streams.push({ scenario, runId: context?.runId ?? 'synthetic-run', signal, emit, finish: gate.resolve });
    return gate.promise;
  });
});

function setup() {
  const attempts: { command: QueueCommand; gate: ReturnType<typeof deferred> }[] = [];
  let id = 0;
  const now = () => Date.parse('2026-10-21T01:00:00+08:00');
  const queuePort = createMockQueuePort({
    now,
    wait: (command) => {
      const gate = deferred();
      attempts.push({ command, gate });
      return gate.promise;
    },
  });
  const queue = createInputQueue(queuePort, 'synthetic-normal', { now, uuid: () => `synthetic-${++id}` });
  const port = createNightPort();
  const hook = renderHook(({ enabled }) => useNormalConversation(port, enabled, queue), {
    initialProps: { enabled: true },
  });
  act(() => streams[0].emit({ type: 'started', run_id: streams[0].runId }));
  return { ...hook, queue, attempts };
}
type Fixture = ReturnType<typeof setup>;
async function enqueue(fixture: Fixture, text: string, images: string[] = []) {
  await act(async () => {
    fixture.result.current.setDraft(text);
    fixture.result.current.setImages(images);
    fixture.result.current.send();
  });
}
async function acknowledge(fixture: Fixture, index = fixture.attempts.length - 1) {
  await act(async () => fixture.attempts[index].gate.resolve());
}
async function complete(stream: StreamGate, answer: string) {
  await act(async () => {
    stream.emit({
      type: 'final',
      envelope: {
        answer,
        professional_appendix: '',
        receipts: [],
        decisions: [],
        evidence: [],
      },
    });
    stream.finish();
  });
}
function begin(stream: StreamGate) {
  act(() => stream.emit({ type: 'started', run_id: stream.runId }));
}

describe('ordinary conversation with the real isolated queue controller and mock port', () => {
  it('clears the original text and images only after the enqueue acknowledgement', async () => {
    const fixture = setup();
    await enqueue(fixture, '补充一', originalImages);
    expect(fixture.result.current.draft).toBe('补充一');
    expect(fixture.result.current.images).toEqual(originalImages);
    expect(fixture.result.current.queued.items[0].state).toBe('pending');
    expect(fixture.result.current.submitting).toBe(true);
    expect(fixture.result.current.prompt).toBe(INITIAL_DEMO_PROMPT);
    expect(streams).toHaveLength(1);
    await acknowledge(fixture);
    expect(fixture.result.current.draft).toBe('');
    expect(fixture.result.current.images).toEqual([]);
    expect(fixture.result.current.queued.items[0]).toMatchObject({
      state: 'queued',
      text: '补充一',
      images: originalImages,
    });
    expect(fixture.attempts[0].command.after_run_id).toBe(streams[0].runId);
  });

  it.each(['后写的新草稿', '补充一'])(
    'preserves a later draft revision and image revision after the old ack: %s',
    async (draft) => {
      const fixture = setup();
      await enqueue(fixture, '补充一', originalImages);
      act(() => {
        fixture.result.current.setDraft(draft);
        fixture.result.current.setImages(nextImages);
      });
      await acknowledge(fixture);
      expect(fixture.result.current.draft).toBe(draft);
      expect(fixture.result.current.images).toEqual(nextImages);
      expect(fixture.result.current.queued.items[0]).toMatchObject({ text: '补充一', images: originalImages });
    },
  );

  it('drains two confirmed messages in FIFO order and retains the earlier completed turns', async () => {
    const fixture = setup();
    await enqueue(fixture, '先收到的补充', originalImages);
    await acknowledge(fixture);
    await enqueue(fixture, '后收到的补充', nextImages);
    await acknowledge(fixture);
    expect(streams).toHaveLength(1);
    await complete(streams[0], '首轮回答');
    expect(streams).toHaveLength(2);
    expect(fixture.result.current.prompt).toBe('先收到的补充');
    expect(fixture.result.current.promptImages).toEqual(originalImages);
    expect(fixture.result.current.turns.map((turn) => turn.state.text)).toEqual(['首轮回答']);
    begin(streams[1]);
    await complete(streams[1], '第一条补充回答');
    expect(streams).toHaveLength(3);
    expect(fixture.result.current.prompt).toBe('后收到的补充');
    expect(fixture.result.current.promptImages).toEqual(nextImages);
    expect(fixture.result.current.turns.map((turn) => turn.state.text)).toEqual(['首轮回答', '第一条补充回答']);
    begin(streams[2]);
    await complete(streams[2], '第二条补充回答');
    expect(fixture.result.current.queued.items).toHaveLength(0);
    expect(fixture.result.current.state.text).toBe('第二条补充回答');
    expect(streams).toHaveLength(3);
  });

  it('cancels exactly the selected queued message after its own receipt', async () => {
    const fixture = setup();
    await enqueue(fixture, '待取消的补充');
    await acknowledge(fixture);
    await enqueue(fixture, '仍要保留的补充');
    await acknowledge(fixture);
    const [first, second] = fixture.result.current.queued.items;
    await act(async () => {
      void fixture.result.current.cancelQueued(first.id);
    });
    expect(fixture.result.current.queued.items.map((item) => item.id)).toEqual([first.id, second.id]);
    expect(fixture.result.current.queued.items[0].state).toBe('canceling');
    expect(fixture.attempts[2].command).toMatchObject({ action: 'cancel', item_id: first.id });
    await acknowledge(fixture);
    expect(fixture.result.current.queued.items.map((item) => item.id)).toEqual([second.id]);
    await complete(streams[0], '首轮回答');
    expect(fixture.result.current.prompt).toBe('仍要保留的补充');
  });

  it('stops synchronously, ignores old events, and requires manual continuation for the remaining queue', async () => {
    const fixture = setup();
    await enqueue(fixture, '第一条排队');
    await acknowledge(fixture);
    await enqueue(fixture, '第二条排队');
    await acknowledge(fixture);
    const stopped = streams[0];
    act(() => {
      stopped.emit({ type: 'text_delta', text: '已展开的片段' });
      fixture.result.current.stop();
    });
    expect(fixture.result.current.reply).toContain('已停止本地演示');
    expect(fixture.result.current.busy).toBe(false);
    expect(fixture.result.current.halted).toBe(true);
    expect(stopped.signal.aborted).toBe(true);
    await complete(stopped, '迟到的不应显示的回答');
    expect(fixture.result.current.state.text).toBe('已展开的片段');
    expect(fixture.result.current.queued.items).toHaveLength(2);
    expect(streams).toHaveLength(1);
    act(() => fixture.result.current.continueQueue());
    expect(fixture.result.current.prompt).toBe('第一条排队');
    expect(fixture.result.current.queued.items.map((item) => item.text)).toEqual(['第二条排队']);
    expect(streams).toHaveLength(2);
    expect(fixture.result.current.turns[0].state.text).toBe('已展开的片段');
  });

  it('keeps queued input while disabled and ignores the old generation after re-entry', async () => {
    const fixture = setup();
    await enqueue(fixture, '离开页面时保留的补充');
    await acknowledge(fixture);
    const old = streams[0];
    act(() => fixture.rerender({ enabled: false }));
    expect(old.signal.aborted).toBe(true);
    await complete(old, '关闭页面后的迟到回答');
    expect(fixture.result.current.state.text).not.toContain('迟到回答');
    expect(fixture.result.current.queued.items).toHaveLength(1);
    act(() => fixture.rerender({ enabled: true }));
    expect(streams).toHaveLength(2);
    begin(streams[1]);
    act(() => old.emit({ type: 'text_delta', text: '旧世代片段' }));
    expect(fixture.result.current.state.text).toBe('');
    await complete(streams[1], '重新进入后的有效回答');
    expect(fixture.result.current.prompt).toBe('离开页面时保留的补充');
    expect(streams).toHaveLength(3);
    expect(fixture.result.current.turns[0].state.text).toBe('重新进入后的有效回答');
  });

  it('does not clear new private-boundary drafts or images when a discarded scope ack arrives', async () => {
    const fixture = setup();
    await enqueue(fixture, '旧会话补充', originalImages);
    const oldScope = fixture.result.current.queued.scope_id;
    act(() => {
      fixture.result.current.clearQueueForPrivacy();
      fixture.result.current.setDraft('切换后的新草稿');
      fixture.result.current.setImages(nextImages);
    });
    expect(fixture.result.current.queued.scope_id).not.toBe(oldScope);
    await acknowledge(fixture);
    expect(fixture.result.current.queued.items).toHaveLength(0);
    expect(fixture.result.current.draft).toBe('切换后的新草稿');
    expect(fixture.result.current.images).toEqual(nextImages);
    expect(fixture.result.current.reply).toBe('');
  });

  it.each([false, true])(
    'retries the original enqueue identity and only clears matching composer versions; edited=%s',
    async (edited) => {
      const fixture = setup();
      await enqueue(fixture, '需要重试的补充', originalImages);
      await act(async () => fixture.attempts[0].gate.reject(new Error('合成接收失败')));
      const failed = fixture.result.current.queued.items[0];
      expect(failed).toMatchObject({ state: 'failed', failed_action: 'enqueue' });
      expect(fixture.result.current.draft).toBe('需要重试的补充');
      if (edited)
        act(() => {
          fixture.result.current.setDraft('重试期间的新草稿');
          fixture.result.current.setImages(nextImages);
        });
      await act(async () => {
        void fixture.result.current.retryQueued(failed.id);
      });
      expect(fixture.attempts[1].command).toEqual(fixture.attempts[0].command);
      await acknowledge(fixture);
      expect(fixture.result.current.queued.items[0]).toMatchObject({
        state: 'queued',
        text: '需要重试的补充',
        images: originalImages,
      });
      expect(fixture.result.current.draft).toBe(edited ? '重试期间的新草稿' : '');
      expect(fixture.result.current.images).toEqual(edited ? nextImages : []);
      expect(fixture.result.current.reply).toBe('');
    },
  );

  it('halts on a terminal error without consuming confirmed input until manual continuation', async () => {
    const fixture = setup();
    await enqueue(fixture, '出错后仍保留的补充');
    await acknowledge(fixture);
    await act(async () => {
      streams[0].emit({ type: 'text_delta', text: '出错前的片段' });
      streams[0].emit({ type: 'error', code: 'SYNTHETIC', message: '合成中断', retryable: true });
      streams[0].finish();
    });
    expect(fixture.result.current.halted).toBe(true);
    expect(fixture.result.current.busy).toBe(false);
    expect(fixture.result.current.queued.items).toHaveLength(1);
    expect(streams).toHaveLength(1);
    act(() => fixture.result.current.continueQueue());
    expect(fixture.result.current.prompt).toBe('出错后仍保留的补充');
    expect(fixture.result.current.turns[0].state).toMatchObject({ text: '出错前的片段', error: '合成中断' });
    expect(streams).toHaveLength(2);
  });

  it.each(['pending', 'failed'] as const)(
    'keeps the manual continuation available while the first enqueue is %s',
    async (headState) => {
      const fixture = setup();
      await enqueue(fixture, '接收确认后再继续的补充');
      if (headState === 'failed') await act(async () => fixture.attempts[0].gate.reject(new Error('合成接收失败')));
      await act(async () => {
        streams[0].emit({ type: 'error', code: 'SYNTHETIC', message: '合成中断', retryable: true });
        streams[0].finish();
      });
      const item = fixture.result.current.queued.items[0];
      act(() => fixture.result.current.continueQueue());
      expect(fixture.result.current.halted).toBe(true);
      expect(fixture.result.current.queued.items[0].state).toBe(headState);
      expect(fixture.result.current.prompt).toBe(INITIAL_DEMO_PROMPT);
      expect(streams).toHaveLength(1);
      if (headState === 'failed')
        await act(async () => {
          void fixture.result.current.retryQueued(item.id);
        });
      await acknowledge(fixture);
      expect(fixture.result.current.halted).toBe(true);
      expect(fixture.result.current.queued.items[0].state).toBe('queued');
      expect(streams).toHaveLength(1);
      act(() => fixture.result.current.continueQueue());
      expect(fixture.result.current.halted).toBe(false);
      expect(fixture.result.current.prompt).toBe('接收确认后再继续的补充');
      expect(streams).toHaveLength(2);
    },
  );
});
