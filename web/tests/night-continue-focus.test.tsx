import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatEvent } from '../src/chat/types';
import { createMemoryReceiptRegistry } from '../src/chat/interactions/memoryProjection';
import ChatPreview from '../src/night/ChatPreview';
import { playDemo } from '../src/night/events';
import { createNightPort } from '../src/night/port';
import { createInputQueue, createMockQueuePort } from '../src/night/queue';
import { useNormalConversation, type NormalConversation } from '../src/night/useNormalConversation';

vi.mock('../src/night/events', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../src/night/events')>()),
  playDemo: vi.fn(),
}));
function gate() {
  let resolve!: () => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<void>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
let frames: Map<number, FrameRequestCallback>, frameId: number;
let streams: { emit: (event: ChatEvent) => void; gate: ReturnType<typeof gate> }[];
beforeEach(() => {
  frames = new Map();
  frameId = 0;
  streams = [];
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    frames.set(++frameId, callback);
    return frameId;
  });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id));
  vi.mocked(playDemo).mockImplementation(async (_scenario, emit, signal) => {
    const pending = gate();
    signal.addEventListener('abort', () => pending.reject(new DOMException('Stopped', 'AbortError')), { once: true });
    streams.push({ emit, gate: pending });
    return pending.promise;
  });
});
afterEach(() => vi.unstubAllGlobals());
function flushFrames() {
  act(() => {
    const batch = [...frames.values()];
    frames.clear();
    for (const callback of batch) callback(0);
  });
}
async function setup(pendingHead = false) {
  const now = () => Date.parse('2026-10-21T09:00:00+08:00');
  const acknowledgement = gate();
  const queue = createInputQueue(
    createMockQueuePort({
      now,
      delay_ms: 0,
      ...(pendingHead ? { wait: () => acknowledgement.promise } : {}),
    }),
    'synthetic-focus-scope',
    { now },
  );
  const first = queue.enqueue({ text: '第一条待取消', images: [], after_run_id: 'synthetic-original' });
  if (!pendingHead) {
    await first;
    await queue.enqueue({ text: '第二条保留', images: [], after_run_id: 'synthetic-original' });
  }
  const port = createNightPort(),
    registry = createMemoryReceiptRegistry();
  let current!: NormalConversation;
  function Harness() {
    current = useNormalConversation(port, true, queue);
    return <ChatPreview port={port} receiptRegistry={registry} chat={current} onPrivacyChange={vi.fn()} />;
  }
  const mounted = render(<Harness />);
  fireEvent.change(screen.getByRole('textbox', { name: '和明镜说说' }), { target: { value: '仍未提交的普通草稿' } });
  await act(async () => current.stop());
  flushFrames();
  return { ...mounted, queue, getChat: () => current, acknowledgement };
}

describe('manual queue continuation focus with the real chat view', () => {
  it('returns focus from the removed continuation button without changing the retained draft or FIFO item', async () => {
    const fixture = await setup();
    const cancel = screen.getAllByRole('button', { name: '取消排队' })[0];
    cancel.focus();
    fireEvent.click(cancel);
    await waitFor(() => expect(screen.getAllByRole('button', { name: '取消排队' })).toHaveLength(1));
    flushFrames();
    const composer = screen.getByRole('textbox', { name: '和明镜说说' });
    expect(composer).toHaveFocus();
    const next = screen.getByRole('button', { name: '继续处理下一条' });
    next.focus();
    fireEvent.click(next);
    expect(next).not.toBeInTheDocument();
    flushFrames();
    expect(composer).toHaveFocus();
    expect(composer).toHaveValue('仍未提交的普通草稿');
    expect(fixture.getChat().prompt).toBe('第二条保留');
    expect(fixture.queue.getSnapshot().items).toHaveLength(0);
    expect(streams).toHaveLength(2);
  });

  it('does not steal focus if the user moves to another connected control before the restoration frame', async () => {
    const fixture = await setup();
    const next = screen.getByRole('button', { name: '继续处理下一条' });
    next.focus();
    fireEvent.click(next);
    const other = screen.getByRole('button', { name: '重放对话' });
    other.focus();
    flushFrames();
    expect(other).toHaveFocus();
    expect(fixture.getChat().prompt).toBe('第一条待取消');
    expect(fixture.queue.getSnapshot().items.map((item) => item.text)).toEqual(['第二条保留']);
    expect(screen.getByRole('textbox', { name: '和明镜说说' })).toHaveValue('仍未提交的普通草稿');
  });

  it('keeps continuation focus and the halted queue when the first message has not been acknowledged', async () => {
    const fixture = await setup(true);
    const next = screen.getByRole('button', { name: '继续处理下一条' });
    next.focus();
    fireEvent.click(next);
    flushFrames();
    expect(next).toHaveFocus();
    expect(next).toBeInTheDocument();
    expect(fixture.getChat().halted).toBe(true);
    expect(fixture.queue.getSnapshot().items[0].state).toBe('pending');
    expect(streams).toHaveLength(1);
    await act(async () => fixture.acknowledgement.resolve());
    expect(fixture.queue.getSnapshot().items[0].state).toBe('queued');
    expect(streams).toHaveLength(1);
  });
});
