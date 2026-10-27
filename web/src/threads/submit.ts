import { abortable, cancelUnusedResponse } from '../chat/followV1Async';
import {
  opaqueThreadId,
  threadAcceptance,
  threadMessage,
  ThreadRequestError,
  type ThreadAcceptance,
} from './contracts';

export type SubmissionOwner = {
  signal: AbortSignal;
  // Caller binds auth epoch, generation, subject and original target thread.
  isCurrent: () => boolean;
  headers: () => HeadersInit;
};
function assertOwner(owner: SubmissionOwner) {
  if (owner.signal.aborted || !owner.isCurrent()) throw new ThreadRequestError('obsolete');
}
async function readReceipt(response: Response, owner: SubmissionOwner): Promise<unknown> {
  if (!response.body) throw new ThreadRequestError('receipt');
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let size = 0,
    result = '';
  try {
    while (true) {
      assertOwner(owner);
      const chunk = await abortable(reader.read(), owner.signal);
      assertOwner(owner);
      if (chunk.done) return JSON.parse(result + decoder.decode()) as unknown;
      size += chunk.value.byteLength;
      if (size > 65536) throw new ThreadRequestError('receipt');
      result += decoder.decode(chunk.value, { stream: true });
    }
  } finally {
    void reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

/** Explicit transport injection; constructing this port never sends or reads storage. */
export function threadSubmitPort(fetcher: typeof fetch) {
  return async function submit(
    target: { threadId: string; incognito: boolean },
    input: unknown,
    owner: SubmissionOwner,
  ): Promise<ThreadAcceptance> {
    assertOwner(owner);
    if (!opaqueThreadId(target.threadId) || ['.', '..'].includes(target.threadId))
      throw new ThreadRequestError('input');
    const payload = threadMessage(input, target.incognito);
    const path = `/api/threads/${encodeURIComponent(target.threadId)}/messages`;
    const headers = new Headers(owner.headers());
    assertOwner(owner);
    headers.set('Content-Type', 'application/json');
    headers.set('Accept', 'application/json');
    const controller = new AbortController();
    const abort = () => controller.abort();
    owner.signal.addEventListener('abort', abort, { once: true });
    const timer = setTimeout(abort, 45000);
    const boundedOwner = { ...owner, signal: controller.signal };
    let response: Response | undefined;
    try {
      assertOwner(owner);
      response = await abortable(
        fetcher(path, {
          method: 'POST',
          headers,
          body: JSON.stringify(payload),
          signal: controller.signal,
          credentials: 'same-origin',
          redirect: 'error',
          cache: 'no-store',
        }),
        controller.signal,
        cancelUnusedResponse,
      );
      assertOwner(owner);
      if (response.status !== 202) throw new ThreadRequestError('http');
      if (!/^application\/json(?:\s*;|$)/i.test(response.headers.get('Content-Type') ?? ''))
        throw new ThreadRequestError('receipt');
      assertOwner(owner);
      const result = threadAcceptance(await readReceipt(response, boundedOwner));
      assertOwner(owner);
      // No automatic follow, resend, guessed v3 events URL, or local identity rewrite.
      return result;
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
  };
}
