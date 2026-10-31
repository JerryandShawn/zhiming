import type {
  InputQueue,
  QueueAck,
  QueueAction,
  QueueCommand,
  QueueInput,
  QueueItem,
  QueueOptions,
  QueuePort,
  QueueResult,
  QueueSnapshot,
} from './types';

type RecordEntry = {
  item: QueueItem;
  enqueue: QueueCommand & { action: 'enqueue' };
  cancel?: QueueCommand & { action: 'cancel' };
  active?: Promise<QueueResult>;
};
const copyInput = (input: QueueInput): QueueInput => ({
  text: input.text.trim(),
  images: Object.freeze([...input.images]),
  after_run_id: input.after_run_id,
});
const identity = (value: string) => typeof value === 'string' && value.trim().length > 0;
function sameInput(a: QueueInput, b: QueueInput) {
  return (
    a.text === b.text &&
    a.after_run_id === b.after_run_id &&
    Array.isArray(a.images) &&
    a.images.length === b.images.length &&
    a.images.every((image, index) => image === b.images[index])
  );
}
export function validQueueAck(value: unknown, command: QueueCommand): value is QueueAck {
  if (!value || typeof value !== 'object') return false;
  const ack = value as QueueAck;
  return (
    ['accepted', 'rejected'].includes(ack.status) &&
    ack.action === command.action &&
    ack.scope_id === command.scope_id &&
    ack.item_id === command.item_id &&
    ack.request_id === command.request_id &&
    sameInput(ack, command) &&
    Number.isSafeInteger(ack.at_ms) &&
    ack.at_ms >= 0 &&
    typeof ack.message === 'string'
  );
}

/** Only confirmed input is claimable. No storage, transport, model or conversation state lives here. */
export function createInputQueue(port: QueuePort, scopeId: string, options: QueueOptions = {}): InputQueue {
  if (!identity(scopeId)) throw new Error('排队会话标识无效。');
  const uuid = options.uuid ?? (() => crypto.randomUUID()),
    now = options.now ?? Date.now;
  const records = new Map<string, RecordEntry>(),
    listeners = new Set<() => void>();
  let scope = scopeId,
    epoch = 0,
    revision = 0,
    order: string[] = [];
  let snapshot: QueueSnapshot = Object.freeze({ scope_id: scope, revision, items: Object.freeze([]) });
  function nextId() {
    const id = uuid();
    if (!identity(id)) throw new Error('排队操作标识无效。');
    return id;
  }
  function publish() {
    snapshot = Object.freeze({
      scope_id: scope,
      revision: ++revision,
      items: Object.freeze(
        order.map((id) => {
          const item = records.get(id)!.item;
          return Object.freeze({ ...item, images: Object.freeze([...item.images]) });
        }),
      ),
    });
    for (const listener of [...listeners]) {
      try {
        listener();
      } catch {
        /* A view cannot reverse an already confirmed queue command. */
      }
    }
  }
  function result(command: QueueCommand, status: QueueResult['status'], message: string): QueueResult {
    return Object.freeze({
      status,
      action: command.action,
      scope_id: command.scope_id,
      item_id: command.item_id,
      request_id: command.request_id,
      message,
    });
  }
  function unavailable(id: string, action: QueueAction, message: string): Promise<QueueResult> {
    return Promise.resolve(
      Object.freeze({ status: 'rejected', action, scope_id: scope, item_id: id, request_id: '', message }),
    );
  }
  function run(entry: RecordEntry, action: QueueAction): Promise<QueueResult> {
    if (entry.active) return entry.active;
    if (action === 'cancel' && !entry.cancel)
      entry.cancel = Object.freeze({ ...entry.enqueue, action: 'cancel', request_id: nextId() });
    const command = action === 'enqueue' ? entry.enqueue : entry.cancel!;
    const capturedEpoch = epoch;
    const current = () => epoch === capturedEpoch && scope === command.scope_id && records.get(entry.item.id) === entry;
    entry.item = {
      ...entry.item,
      state: action === 'enqueue' ? 'pending' : 'canceling',
      error: undefined,
      failed_action: undefined,
    };
    publish();
    const task = Promise.resolve().then(async (): Promise<QueueResult> => {
      try {
        const ack = await (command.action === 'enqueue' ? port.enqueue(command) : port.cancel(command));
        if (!current()) return result(command, 'stale', '旧会话的排队回执已忽略。');
        if (!validQueueAck(ack, command)) throw new Error('尚未收到这条消息的有效确认，请重试。');
        if (ack.status !== 'accepted') throw new Error(ack.message || '这次排队操作尚未确认，请重试。');
        if (action === 'enqueue')
          entry.item = { ...entry.item, state: 'queued', error: undefined, failed_action: undefined };
        else {
          records.delete(entry.item.id);
          order = order.filter((id) => id !== entry.item.id);
        }
        publish();
        return result(command, 'accepted', ack.message);
      } catch (reason) {
        if (!current()) return result(command, 'stale', '旧会话的排队回执已忽略。');
        const message = reason instanceof Error ? reason.message : '排队操作暂未确认，请重试。';
        entry.item = { ...entry.item, state: 'failed', error: message, failed_action: action };
        publish();
        return result(command, 'rejected', message);
      } finally {
        if (entry.active === task) entry.active = undefined;
      }
    });
    entry.active = task;
    return task;
  }
  return {
    getSnapshot: () => snapshot,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    enqueue(input) {
      if (
        !input ||
        !identity(input.text) ||
        !identity(input.after_run_id) ||
        !Array.isArray(input.images) ||
        input.images.length > 4 ||
        input.images.some((image) => typeof image !== 'string' || !image)
      )
        return unavailable('', 'enqueue', '先写下消息，并核对本轮附图。');
      const id = nextId(),
        request_id = nextId(),
        at = now();
      if (records.has(id) || !Number.isSafeInteger(at) || at < 0)
        return unavailable(id, 'enqueue', '排队标识或本地时间无效，请重试。');
      const value = copyInput(input);
      const command = Object.freeze({ ...value, scope_id: scope, item_id: id, request_id, action: 'enqueue' as const });
      const entry: RecordEntry = {
        enqueue: command,
        item: { ...value, id, request_id, created_at_ms: at, state: 'pending' },
      };
      records.set(id, entry);
      order.push(id);
      return run(entry, 'enqueue');
    },
    retry(id) {
      const entry = records.get(id);
      if (!entry) return unavailable(id, 'enqueue', '这条消息已不在当前排队列表。');
      if (entry.active) return entry.active;
      if (entry.item.state !== 'failed') return unavailable(id, 'enqueue', '这条消息不需要重试。');
      return run(entry, entry.item.failed_action ?? 'enqueue');
    },
    cancel(id) {
      const entry = records.get(id);
      if (!entry) return unavailable(id, 'cancel', '这条消息已开始处理或已离开排队列表。');
      if (entry.active || entry.item.state === 'pending' || entry.item.state === 'canceling')
        return unavailable(id, 'cancel', '请等当前接收或取消操作确认后再试。');
      return run(entry, 'cancel');
    },
    claimNext() {
      const entry = records.get(order[0]);
      if (!entry || entry.item.state !== 'queued') return undefined;
      const item = Object.freeze({ ...entry.item, images: Object.freeze([...entry.item.images]) });
      records.delete(item.id);
      order.shift();
      publish();
      return item;
    },
    reset(nextScope) {
      if (!identity(nextScope)) throw new Error('排队会话标识无效。');
      ++epoch;
      scope = nextScope;
      records.clear();
      order = [];
      publish();
    },
  };
}
