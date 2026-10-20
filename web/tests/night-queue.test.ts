import { describe, expect, it, vi } from 'vitest';
import { createInputQueue, createMockQueuePort, validQueueAck } from '../src/night/queue';
import type { QueueAck, QueueCommand, QueueInput, QueuePort } from '../src/night/queue';

const time = Date.parse('2026-10-21T02:00:00+08:00');
const input = (text = '后面再聊这一条'): QueueInput => ({ text, images: ['synthetic-image'], after_run_id: 'run-1' });
const options = () => {
  let id = 0;
  return { now: () => time, uuid: () => `queue-${++id}` };
};
const mockPort = () => createMockQueuePort({ delay_ms: 0, now: () => time });
const flush = async () => {
  await Promise.resolve();
  await Promise.resolve();
};
function deferredPort() {
  const pending: { command: QueueCommand; resolve: (ack: QueueAck) => void; reject: (reason: Error) => void }[] = [];
  const execute = (command: QueueCommand) =>
    new Promise<QueueAck>((resolve, reject) => {
      pending.push({ command, resolve, reject });
    });
  const port: QueuePort = { enqueue: vi.fn(execute), cancel: vi.fn(execute) };
  const accept = (index: number, patch: Partial<QueueAck> = {}) =>
    pending[index].resolve({
      ...pending[index].command,
      status: 'accepted',
      at_ms: time,
      message: '本地已确认',
      ...patch,
    });
  return { port, pending, accept };
}

describe('ordinary demo input queue acknowledgement boundary', () => {
  it('does not claim pending input and claims each accepted message exactly once in FIFO order', async () => {
    const deferred = deferredPort(),
      queue = createInputQueue(deferred.port, 'ordinary-1', options());
    const first = queue.enqueue(input('第一条')),
      second = queue.enqueue(input('第二条'));
    expect(queue.getSnapshot().items.map((item) => item.state)).toEqual(['pending', 'pending']);
    expect(queue.claimNext()).toBeUndefined();
    await flush();
    deferred.accept(1);
    expect((await second).status).toBe('accepted');
    expect(queue.claimNext()).toBeUndefined();
    deferred.accept(0);
    await first;
    expect(queue.claimNext()?.text).toBe('第一条');
    expect(queue.claimNext()?.text).toBe('第二条');
    expect(queue.claimNext()).toBeUndefined();
  });

  it('copies inputs and freezes stable snapshots, including attachment arrays', async () => {
    const source = { ...input(), images: ['original-image'] },
      queue = createInputQueue(mockPort(), 'ordinary-1', options());
    const empty = queue.getSnapshot(),
      sending = queue.enqueue(source);
    source.images.push('later-image');
    source.text = 'later text';
    expect(queue.getSnapshot()).not.toBe(empty);
    expect(queue.getSnapshot()).toBe(queue.getSnapshot());
    await sending;
    const snapshot = queue.getSnapshot(),
      item = snapshot.items[0];
    expect(item.images).toEqual(['original-image']);
    expect(item.text).toBe('后面再聊这一条');
    expect(Object.isFrozen(snapshot)).toBe(true);
    expect(Object.isFrozen(snapshot.items)).toBe(true);
    expect(Object.isFrozen(item.images)).toBe(true);
    expect(() => (item.images as string[]).push('mutated')).toThrow();
  });

  it.each(['scope_id', 'item_id', 'request_id', 'action', 'after_run_id', 'text', 'images', 'at_ms'] as const)(
    'retains a failed row and retries the original command when %s acknowledgement is wrong',
    async (field) => {
      const deferred = deferredPort(),
        queue = createInputQueue(deferred.port, 'ordinary-1', options());
      const sending = queue.enqueue(input());
      await flush();
      const patch = { [field]: field === 'images' ? ['wrong-image'] : field === 'at_ms' ? NaN : 'wrong' };
      deferred.accept(0, patch);
      expect((await sending).status).toBe('rejected');
      const failed = queue.getSnapshot().items[0];
      expect(failed).toMatchObject({ state: 'failed', failed_action: 'enqueue', text: input().text });
      expect(queue.claimNext()).toBeUndefined();
      const retry = queue.retry(failed.id),
        duplicate = queue.retry(failed.id);
      expect(retry).toBe(duplicate);
      await flush();
      expect(deferred.pending[1].command).toEqual(deferred.pending[0].command);
      deferred.accept(1);
      expect((await retry).status).toBe('accepted');
      expect(queue.claimNext()?.id).toBe(failed.id);
    },
  );

  it('retains transport failures and rejected acknowledgements until retry or confirmed cancellation', async () => {
    const deferred = deferredPort(),
      queue = createInputQueue(deferred.port, 'ordinary-1', options());
    const sending = queue.enqueue(input());
    await flush();
    deferred.pending[0].reject(new Error('模拟连接抖动'));
    expect((await sending).status).toBe('rejected');
    const id = queue.getSnapshot().items[0].id,
      retry = queue.retry(id);
    await flush();
    deferred.accept(1, { status: 'rejected', message: '请稍后重试' });
    expect((await retry).status).toBe('rejected');
    expect(queue.getSnapshot().items[0].error).toBe('请稍后重试');
    const cancel = queue.cancel(id);
    await flush();
    deferred.accept(2);
    expect((await cancel).status).toBe('accepted');
    expect(queue.getSnapshot().items).toHaveLength(0);
  });

  it('cancels only the selected item and never consumes its neighbors', async () => {
    const queue = createInputQueue(mockPort(), 'ordinary-1', options());
    await queue.enqueue(input('第一条'));
    await queue.enqueue(input('第二条'));
    await queue.enqueue(input('第三条'));
    const [first, second, third] = queue.getSnapshot().items;
    expect((await queue.cancel(second.id)).status).toBe('accepted');
    expect(queue.getSnapshot().items.map((item) => item.id)).toEqual([first.id, third.id]);
    expect(queue.claimNext()?.id).toBe(first.id);
    expect((await queue.cancel(first.id)).status).toBe('rejected');
    expect(queue.claimNext()?.id).toBe(third.id);
  });

  it('blocks a canceling or failed head, retries cancellation with its stable request id', async () => {
    const deferred = deferredPort(),
      queue = createInputQueue(deferred.port, 'ordinary-1', options());
    const sending = queue.enqueue(input());
    await flush();
    deferred.accept(0);
    await sending;
    const id = queue.getSnapshot().items[0].id,
      cancel = queue.cancel(id);
    expect(queue.getSnapshot().items[0].state).toBe('canceling');
    expect(queue.claimNext()).toBeUndefined();
    await flush();
    deferred.pending[1].reject(new Error('取消尚未确认'));
    expect((await cancel).status).toBe('rejected');
    expect(queue.getSnapshot().items[0]).toMatchObject({ state: 'failed', failed_action: 'cancel' });
    expect(queue.claimNext()).toBeUndefined();
    const retry = queue.retry(id);
    await flush();
    expect(deferred.pending[2].command).toEqual(deferred.pending[1].command);
    expect(deferred.pending[2].command.request_id).not.toBe(deferred.pending[0].command.request_id);
    deferred.accept(2);
    await retry;
    expect(queue.getSnapshot().items).toHaveLength(0);
  });

  it.each(['enqueue', 'cancel'] as const)('discards a late %s receipt after scope reset', async (action) => {
    const deferred = deferredPort(),
      queue = createInputQueue(deferred.port, 'ordinary-1', options());
    let operation = queue.enqueue(input());
    await flush();
    let index = 0;
    if (action === 'cancel') {
      deferred.accept(0);
      await operation;
      operation = queue.cancel(queue.getSnapshot().items[0].id);
      await flush();
      index = 1;
    }
    queue.reset('ordinary-2');
    const clean = queue.getSnapshot();
    deferred.accept(index);
    expect((await operation).status).toBe('stale');
    expect(queue.getSnapshot()).toBe(clean);
    expect(queue.getSnapshot().items).toHaveLength(0);
  });

  it('invalidates late failures even when resetting to the same scope identifier', async () => {
    const deferred = deferredPort(),
      queue = createInputQueue(deferred.port, 'ordinary-1', options());
    const sending = queue.enqueue(input());
    await flush();
    queue.reset('ordinary-1');
    const clean = queue.getSnapshot();
    deferred.pending[0].reject(new Error('OLD_FAILURE'));
    expect((await sending).status).toBe('stale');
    expect(queue.getSnapshot()).toBe(clean);
  });

  it('does not allow cancellation before enqueue acknowledgement or invalid input', async () => {
    const deferred = deferredPort(),
      queue = createInputQueue(deferred.port, 'ordinary-1', options());
    expect((await queue.enqueue(input('  '))).status).toBe('rejected');
    expect((await queue.enqueue({ ...input(), images: Array(5).fill('image') })).status).toBe('rejected');
    expect(queue.getSnapshot().items).toHaveLength(0);
    const sending = queue.enqueue(input());
    const id = queue.getSnapshot().items[0].id;
    expect((await queue.cancel(id)).status).toBe('rejected');
    await flush();
    deferred.accept(0);
    await sending;
    expect(deferred.port.cancel).not.toHaveBeenCalled();
    expect(queue.getSnapshot().items[0].state).toBe('queued');
  });

  it('does not lose committed queue state when a view observer throws', async () => {
    const queue = createInputQueue(mockPort(), 'ordinary-1', options());
    const unsubscribe = queue.subscribe(() => {
      throw new Error('unmounted view');
    });
    expect((await queue.enqueue(input())).status).toBe('accepted');
    unsubscribe();
    expect(queue.claimNext()?.text).toBe(input().text);
  });
});

describe('replaceable mock queue port', () => {
  const command = (): QueueCommand & { action: 'enqueue' } => ({
    ...input(),
    action: 'enqueue',
    scope_id: 'ordinary-1',
    item_id: 'item-1',
    request_id: 'request-1',
  });
  it('has stable replay receipts and rejects altered payload under an existing request identity', async () => {
    const port = mockPort(),
      original = command();
    const ack = await port.enqueue(original);
    expect(await port.enqueue(original)).toBe(ack);
    expect(validQueueAck(ack, original)).toBe(true);
    expect((await port.enqueue({ ...original, text: 'changed' })).status).toBe('rejected');
    expect((await port.enqueue({ ...original, text: 'changed' })).code).toBe('REPLAY_CHANGED');
  });
  it('allows transport retry under the same identity after an injected failure', async () => {
    const wait = vi.fn().mockRejectedValueOnce(new Error('simulated failure')).mockResolvedValue(undefined);
    const port = createMockQueuePort({ wait, now: () => time }),
      original = command();
    await expect(port.enqueue(original)).rejects.toThrow('simulated failure');
    expect((await port.enqueue(original)).status).toBe('accepted');
    expect(wait).toHaveBeenCalledTimes(2);
  });
  it('isolates identical item ids by scope and never resurrects a confirmed canceled item', async () => {
    const port = mockPort(),
      original = command();
    await port.cancel({ ...original, action: 'cancel', request_id: 'cancel-1' });
    expect((await port.enqueue(original)).code).toBe('CANCELED');
    expect((await port.enqueue({ ...original, scope_id: 'ordinary-2' })).status).toBe('accepted');
  });
});
