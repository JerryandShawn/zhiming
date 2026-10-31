import {
  opaqueThreadId,
  threadAcceptance,
  threadMessage,
  ThreadRequestError,
  type ThreadAcceptance,
} from './contracts';
import { assertOwner, ownedJson, type RequestOwner } from './request';

export type SubmissionOwner = RequestOwner;

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
    const value = await ownedJson(
      fetcher,
      `/api/threads/${encodeURIComponent(target.threadId)}/messages`,
      { method: 'POST', status: 202, maxBytes: 65536, body: payload },
      owner,
    );
    const accepted = threadAcceptance(value);
    assertOwner(owner);
    return accepted;
  };
}
