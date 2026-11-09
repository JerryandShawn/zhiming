import type { MockQueueOptions, QueueAck, QueueCommand, QueuePort } from './types';

/** A replaceable in-memory acknowledgement boundary. It has no HTTP or persistent storage. */
export function createMockQueuePort(options: MockQueueOptions = {}): QueuePort {
  const now = options.now ?? Date.now;
  const requests = new Map<string, { signature: string; result: Promise<QueueAck> }>();
  const items = new Map<string, { payload: string; canceled: boolean }>();
  const payload = (command: QueueCommand) => JSON.stringify([command.after_run_id, command.text, command.images]);
  function ack(command: QueueCommand, status: QueueAck['status'], code?: string): QueueAck {
    return Object.freeze({
      ...command,
      images: Object.freeze([...command.images]),
      status,
      at_ms: now(),
      message:
        status === 'accepted'
          ? command.action === 'enqueue'
            ? '已收到，这段说完一起看。'
            : '已取消这条排队消息。'
          : '这条排队消息的操作内容已变化，请重新核对。',
      ...(code ? { code } : {}),
    });
  }
  function execute(input: QueueCommand): Promise<QueueAck> {
    const command = Object.freeze({ ...input, images: Object.freeze([...input.images]) });
    const requestKey = JSON.stringify([command.scope_id, command.request_id]);
    const signature = JSON.stringify(command),
      previous = requests.get(requestKey);
    if (previous)
      return previous.signature === signature
        ? previous.result
        : Promise.resolve(ack(command, 'rejected', 'REPLAY_CHANGED'));
    const result = Promise.resolve()
      .then(async () => {
        if (options.wait) await options.wait(command);
        else if ((options.delay_ms ?? 150) > 0)
          await new Promise<void>((resolve) => setTimeout(resolve, options.delay_ms ?? 150));
        const key = JSON.stringify([command.scope_id, command.item_id]);
        const existing = items.get(key),
          value = payload(command);
        if (existing && existing.payload !== value) return ack(command, 'rejected', 'ITEM_CHANGED');
        if (command.action === 'enqueue' && existing?.canceled) return ack(command, 'rejected', 'CANCELED');
        items.set(key, { payload: value, canceled: command.action === 'cancel' });
        return ack(command, 'accepted');
      })
      .catch((reason: unknown) => {
        // A failed transport attempt has no receipt. Retrying keeps the original command identity.
        requests.delete(requestKey);
        throw reason;
      });
    requests.set(requestKey, { signature, result });
    return result;
  }
  return { enqueue: execute, cancel: execute };
}
