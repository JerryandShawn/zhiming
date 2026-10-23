export type QueueInput = { text: string; images: readonly string[]; after_run_id: string };
export type QueueAction = 'enqueue' | 'cancel';
export type QueueItem = QueueInput & {
  id: string;
  request_id: string;
  created_at_ms: number;
  state: 'pending' | 'queued' | 'canceling' | 'failed';
  error?: string;
  failed_action?: QueueAction;
};
export type QueueSnapshot = { scope_id: string; revision: number; items: readonly QueueItem[] };
export type QueueCommand = QueueInput & {
  action: QueueAction;
  scope_id: string;
  item_id: string;
  request_id: string;
};
export type QueueAck = QueueCommand & {
  status: 'accepted' | 'rejected';
  at_ms: number;
  message: string;
  code?: string;
};
export type QueuePort = {
  enqueue(command: QueueCommand & { action: 'enqueue' }): Promise<QueueAck>;
  cancel(command: QueueCommand & { action: 'cancel' }): Promise<QueueAck>;
};
export type QueueResult = {
  status: 'accepted' | 'rejected' | 'stale';
  action: QueueAction;
  scope_id: string;
  item_id: string;
  request_id: string;
  message: string;
};
export type InputQueue = {
  getSnapshot(): QueueSnapshot;
  subscribe(listener: () => void): () => void;
  enqueue(input: QueueInput): Promise<QueueResult>;
  retry(itemId: string): Promise<QueueResult>;
  cancel(itemId: string): Promise<QueueResult>;
  claimNext(): QueueItem | undefined;
  reset(scopeId: string): void;
};
export type QueueOptions = { uuid?: () => string; now?: () => number };
export type MockQueueOptions = {
  now?: () => number;
  delay_ms?: number;
  wait?: (command: QueueCommand) => Promise<void>;
};
