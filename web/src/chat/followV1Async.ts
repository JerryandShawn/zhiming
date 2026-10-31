/** Late asynchronous work cannot regain ownership after its caller has aborted. */
export function abortable<T>(work: Promise<T>, signal: AbortSignal, discard?: (value: T) => void): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    let settled = false;
    const abort = () => {
      if (settled) return;
      settled = true;
      signal.removeEventListener('abort', abort);
      reject(signal.reason ?? new DOMException('已停止连接', 'AbortError'));
    };
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
    void work.then(
      (value) => {
        if (settled) {
          discard?.(value);
          return;
        }
        settled = true;
        signal.removeEventListener('abort', abort);
        resolve(value);
      },
      (reason: unknown) => {
        if (settled) return;
        settled = true;
        signal.removeEventListener('abort', abort);
        reject(reason);
      },
    );
  });
}

export function retryDelay(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    signal.throwIfAborted();
    const abort = () => {
      clearTimeout(timer);
      signal.removeEventListener('abort', abort);
      reject(signal.reason ?? new DOMException('已停止连接', 'AbortError'));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', abort);
      resolve();
    }, milliseconds);
    signal.addEventListener('abort', abort, { once: true });
  });
}

export function cancelUnusedResponse(response: Response) {
  void response.body?.cancel().catch(() => undefined);
}
