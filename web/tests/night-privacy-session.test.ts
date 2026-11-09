import { afterEach, describe, expect, it, vi } from 'vitest';
import { createPrivacySession, privacyIdleMs } from '../src/night/privacy/session';
import { privateEvent, type PrivatePort } from '../src/night/privacy/port';

afterEach(() => vi.useRealTimers());

function deferredPort() {
  let accept: (event: unknown) => void = () => undefined;
  let finish: () => void = () => undefined;
  let signal: AbortSignal | undefined;
  const port: PrivatePort = {
    respond: vi.fn((_request, receive, abort) => {
      accept = receive;
      signal = abort;
      return new Promise<void>((resolve) => {
        finish = resolve;
      });
    }),
  };
  return { port, event: (value: unknown) => accept(value), finish: () => finish(), signal: () => signal };
}

describe('isolated in-memory incognito conversation', () => {
  it('creates a fresh UUID thread and clears all draft, images and messages on exit', () => {
    const local = createPrivacySession();
    local.enter();
    const first = local.getSnapshot().session!;
    expect(first.id).toMatch(/^incognito:[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/);
    local.setDraft(first, '合成私有草稿');
    local.setImages(first, ['data:image/png;base64,cHJpdmF0ZQ==']);
    local.exit();
    expect(local.getSnapshot()).toEqual({ session: null, endedBy: 'exit' });
    local.enter();
    const second = local.getSnapshot().session!;
    expect(second.id).not.toBe(first.id);
    expect(second).toMatchObject({ draft: '', images: [], messages: [] });
    local.setDraft(first, '迟到的旧会话草稿');
    local.setImages(first, ['PRIVATE_IMAGE']);
    expect(local.getSnapshot().session).toMatchObject({ draft: '', images: [] });
  });

  it('rejects late stream events and completion after exit and re-entry', async () => {
    const deferred = deferredPort();
    const local = createPrivacySession({ port: deferred.port });
    local.enter();
    const first = local.getSnapshot().session!;
    local.setDraft(first, '合成私有问题');
    const sending = local.send(first);
    expect(local.getSnapshot().session?.busy).toBe(true);
    local.exit();
    expect(deferred.signal()?.aborted).toBe(true);
    local.enter();
    const next = local.getSnapshot().session;
    deferred.event({ type: 'text_delta', text: 'LATE_PRIVATE_ANSWER' });
    deferred.event({ type: 'final', text: 'LATE_PRIVATE_FINAL' });
    deferred.finish();
    await sending;
    expect(local.getSnapshot().session).toBe(next);
    expect(JSON.stringify(local.getSnapshot())).not.toMatch(/LATE_PRIVATE|合成私有问题/);
  });

  it('never accepts memory receipts, tool receipts or a final envelope', async () => {
    const deferred = deferredPort();
    const local = createPrivacySession({ port: deferred.port });
    local.enter();
    const session = local.getSnapshot().session!;
    local.setDraft(session, '只在本页的合成问题');
    const sending = local.send(session);
    for (const event of [
      { type: 'memory_receipt', receipt: { summary: 'PRIVATE_FACT' } },
      { type: 'tool_result', receipt: { summary: 'PRIVATE_TOOL_FACT' } },
      { type: 'final', envelope: { text: 'PRIVATE_ENVELOPE', receipts: [{ summary: 'PRIVATE_FINAL_FACT' }] } },
    ])
      deferred.event(event);
    deferred.event({ type: 'text_delta', text: '本地片段' });
    deferred.event({ type: 'text_reset', text: '本地修订' });
    deferred.event({ type: 'final', text: '本地结果', receipts: [{ summary: 'PRIVATE_FINAL_FACT' }] });
    deferred.finish();
    await sending;
    expect(local.getSnapshot().session?.messages[1].text).toBe('本地结果');
    expect(JSON.stringify(local.getSnapshot())).not.toMatch(/PRIVATE_|receipt|fact/);
    expect(privateEvent({ type: 'final', text: '公开本地结果', arbitrary: 'PRIVATE_EXTRA' })).toEqual({
      type: 'final',
      text: '公开本地结果',
    });
  });

  it('stops the current stream and ignores late content without destroying the visible private turn', async () => {
    const deferred = deferredPort();
    const local = createPrivacySession({ port: deferred.port });
    local.enter();
    const session = local.getSnapshot().session!;
    local.setDraft(session, '合成停止问题');
    const sending = local.send(session);
    deferred.event({ type: 'text_delta', text: '已经显示的片段' });
    local.stop(session);
    deferred.event({ type: 'text_delta', text: 'LATE_AFTER_STOP' });
    deferred.finish();
    await sending;
    expect(local.getSnapshot().session).toMatchObject({ busy: false });
    expect(local.getSnapshot().session?.messages[1].text).toBe('已经显示的片段');
    expect(local.getSnapshot().session?.messages[0].text).toBe('合成停止问题');
    expect(deferred.signal()?.aborted).toBe(true);
  });

  it('expires at exactly 24 hours of inactivity, with activity extending the deadline', () => {
    let clock = 0;
    const local = createPrivacySession({ now: () => clock });
    local.enter();
    const session = local.getSnapshot().session!;
    clock = privacyIdleMs - 1;
    local.expire();
    expect(local.getSnapshot().session).not.toBeNull();
    local.setDraft(session, '合成活动');
    clock += privacyIdleMs - 1;
    local.expire();
    expect(local.getSnapshot().session?.draft).toBe('合成活动');
    clock += 1;
    local.expire();
    expect(local.getSnapshot()).toEqual({ session: null, endedBy: 'idle' });
  });

  it('checks inactivity again when a suspended tab receives a late asynchronous result', async () => {
    let clock = 0;
    const deferred = deferredPort();
    const local = createPrivacySession({ now: () => clock, port: deferred.port });
    local.enter();
    const session = local.getSnapshot().session!;
    local.setDraft(session, '合成后台问题');
    const sending = local.send(session);
    clock = privacyIdleMs;
    deferred.event({ type: 'final', text: 'PRIVATE_BACKGROUND_RESULT' });
    deferred.finish();
    await sending;
    expect(local.getSnapshot()).toEqual({ session: null, endedBy: 'idle' });
    expect(deferred.signal()?.aborted).toBe(true);
  });

  it('uses no browser storage or network, including default local response and textual exit', async () => {
    vi.useFakeTimers();
    const storage = vi.spyOn(Storage.prototype, 'setItem');
    const network = vi.spyOn(globalThis, 'fetch');
    const local = createPrivacySession();
    local.enter();
    const session = local.getSnapshot().session!;
    local.setDraft(session, 'PRIVATE_SYNTHETIC_SENTINEL');
    local.setImages(session, ['data:image/png;base64,UFJJVkFURQ==']);
    const sending = local.send(session);
    await vi.runAllTimersAsync();
    await sending;
    expect(local.getSnapshot().session?.messages[1].text).toMatch(/没有连接模型/);
    local.setDraft(session, '结束无痕');
    await local.send(session);
    expect(local.getSnapshot().session).toBeNull();
    expect(storage).not.toHaveBeenCalled();
    expect(network).not.toHaveBeenCalled();
  });
});
