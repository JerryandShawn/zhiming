import { abortable, cancelUnusedResponse } from '../chat/followV1Async';
import { ThreadRequestError } from './contracts';

export type RequestOwner = {
  signal: AbortSignal;
  // Caller binds auth epoch, generation, subject and original target thread.
  isCurrent: () => boolean;
  headers: () => HeadersInit;
};
export function assertOwner(owner: RequestOwner) {
  if (owner.signal.aborted || !owner.isCurrent()) throw new ThreadRequestError('obsolete');
}
export async function readJson(response: Response, owner: RequestOwner, maxBytes: number): Promise<unknown> {
  if (!response.body) throw new ThreadRequestError('receipt');
  const reader = response.body.getReader(),
    decoder = new TextDecoder('utf-8', { fatal: true });
  let size = 0,
    text = '';
  try {
    while (true) {
      assertOwner(owner);
      const chunk = await abortable(reader.read(), owner.signal);
      assertOwner(owner);
      if (chunk.done) return JSON.parse(text + decoder.decode()) as unknown;
      size += chunk.value.byteLength;
      if (size > maxBytes) throw new ThreadRequestError('receipt');
      text += decoder.decode(chunk.value, { stream: true });
    }
  } finally {
    void reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

/** Caller supplies only a prevalidated same-origin endpoint. No retries or global auth side effects. */
export async function ownedJson(
  fetcher: typeof fetch,
  path: string,
  request: { method: 'GET' | 'POST'; status: 200 | 202; maxBytes: number; body?: unknown },
  owner: RequestOwner,
): Promise<unknown> {
  assertOwner(owner);
  const endpoint = new URL(path, 'https://request.invalid');
  if (
    !path.startsWith('/api/') ||
    endpoint.origin !== 'https://request.invalid' ||
    endpoint.pathname !== path ||
    endpoint.search ||
    endpoint.hash
  )
    throw new ThreadRequestError('input');
  const headers = new Headers(owner.headers());
  assertOwner(owner);
  headers.set('Accept', 'application/json');
  if (request.body !== undefined) headers.set('Content-Type', 'application/json');
  const controller = new AbortController();
  const abort = () => controller.abort();
  owner.signal.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(abort, 45000);
  let response: Response | undefined;
  try {
    assertOwner(owner);
    response = await abortable(
      fetcher(path, {
        method: request.method,
        headers,
        ...(request.body === undefined ? {} : { body: JSON.stringify(request.body) }),
        signal: controller.signal,
        credentials: 'same-origin',
        cache: 'no-store',
        redirect: 'error',
      }),
      controller.signal,
      cancelUnusedResponse,
    );
    assertOwner(owner);
    if (response.status !== request.status) throw new ThreadRequestError('http', response.status);
    if (!/^application\/json(?:\s*;|$)/i.test(response.headers.get('Content-Type') ?? ''))
      throw new ThreadRequestError('receipt');
    assertOwner(owner);
    const value = await readJson(response, { ...owner, signal: controller.signal }, request.maxBytes);
    assertOwner(owner);
    return value;
  } catch (error) {
    assertOwner(owner);
    if (controller.signal.aborted) throw new ThreadRequestError('network');
    if (error instanceof ThreadRequestError) throw error;
    throw new ThreadRequestError(response ? 'receipt' : 'network');
  } finally {
    clearTimeout(timer);
    owner.signal.removeEventListener('abort', abort);
    if (response) cancelUnusedResponse(response);
  }
}
