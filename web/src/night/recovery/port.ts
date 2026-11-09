import { RECOVERY_RUN_ID, recoveryChunks } from './events';
import type { RecoveryOptions, RecoveryPort } from './types';

export const RECOVERY_FIXTURE_PATH = `/__frontend_fixture__/events-v1/${RECOVERY_RUN_ID}/events`;

function syntheticStream(chunks: string[], milliseconds: number): Response {
  let timer: ReturnType<typeof setTimeout> | undefined,
    closed = false,
    index = 0;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const next = () => {
        if (closed) return;
        if (index >= chunks.length) {
          closed = true;
          controller.close();
          return;
        }
        controller.enqueue(new TextEncoder().encode(chunks[index++]));
        timer = setTimeout(next, milliseconds);
      };
      next();
    },
    cancel() {
      closed = true;
      clearTimeout(timer);
    },
  });
  return new Response(body, { headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store' } });
}

/** Default adapter has no fetch, persistent store, credentials or server route. */
export function createRecoveryPort(options: RecoveryOptions = {}): RecoveryPort {
  let rejected = false;
  const delay = options.delayMs ?? 120;
  if (!Number.isFinite(delay) || delay < 0 || delay > 10000) throw new Error('本地演示等待时间无效。');
  return {
    runId: RECOVERY_RUN_ID,
    mode: 'memory',
    async connect(lastEventId, signal) {
      signal.throwIfAborted();
      if ((options.rejectFirst ?? true) && !rejected) {
        rejected = true;
        throw new Error('合成连接暂时断开');
      }
      return syntheticStream(recoveryChunks(Number(lastEventId) >= 3, options.now), delay);
    },
  };
}

export function localRecoveryTransportAllowed(url: URL) {
  return (
    ['http:', 'https:'].includes(url.protocol) &&
    ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) &&
    url.searchParams.get('recoveryTransport') === 'local-fixture'
  );
}

/** Opt-in loopback HTTP fixture only; this is deliberately outside every backend proxy prefix. */
export function recoveryPortForLocation(url: URL, fetcher: typeof fetch = fetch): RecoveryPort {
  if (!localRecoveryTransportAllowed(url)) return createRecoveryPort();
  const endpoint = new URL(RECOVERY_FIXTURE_PATH, url.origin);
  return {
    runId: RECOVERY_RUN_ID,
    mode: 'local-fixture',
    async connect(lastEventId, signal) {
      signal.throwIfAborted();
      if (lastEventId !== undefined && !/^[1-9]\d*$/.test(lastEventId)) throw new Error('恢复位置尚未核对。');
      const headers = new Headers({ Accept: 'text/event-stream' });
      if (lastEventId) headers.set('Last-Event-ID', lastEventId);
      return fetcher(endpoint, { signal, headers, credentials: 'omit', cache: 'no-store' });
    },
  };
}
