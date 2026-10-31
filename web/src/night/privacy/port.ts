export type PrivateEvent =
  { type: 'text_delta'; text: string } | { type: 'text_reset'; text: string } | { type: 'final'; text: string };

export type PrivateRequest = { threadId: string; text: string; images: readonly string[] };
export type PrivatePort = {
  respond: (request: PrivateRequest, accept: (event: unknown) => void, signal: AbortSignal) => Promise<void>;
};

// This adapter has no memory commands, ordinary conversation port or storage dependency.
export function createPrivatePort(): PrivatePort {
  return {
    async respond(_request, accept, signal) {
      const text = '我在听。你可以先说最想理清的那一件事。这是本地演示，没有连接模型。';
      for (const part of [text.slice(0, 15), text.slice(15)]) {
        signal.throwIfAborted();
        await new Promise<void>((resolve, reject) => {
          const abort = () => {
            clearTimeout(timer);
            reject(new DOMException('无痕演示已停止', 'AbortError'));
          };
          const timer = setTimeout(() => {
            signal.removeEventListener('abort', abort);
            resolve();
          }, 80);
          signal.addEventListener('abort', abort, { once: true });
        });
        signal.throwIfAborted();
        accept({ type: 'text_delta', text: part });
      }
      accept({ type: 'final', text });
    },
  };
}

export function privateEvent(value: unknown): PrivateEvent | undefined {
  if (!value || typeof value !== 'object') return;
  const event = value as Record<string, unknown>;
  if (['text_delta', 'text_reset', 'final'].includes(String(event.type)) && typeof event.text === 'string')
    return { type: event.type as PrivateEvent['type'], text: event.text };
}
