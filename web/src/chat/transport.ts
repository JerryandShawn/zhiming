import { api, authHeaders, requireLogin } from '../api/client';
import { chatEvent } from './events';
import { readSse } from './sse';
import { assertCurrentChat, storePending } from './storage';
import { object, type ChatEvent, type PendingChat, type Run } from './types';

async function streamRequest(
  path: string,
  payload: unknown,
  pending: PendingChat,
  signal: AbortSignal,
): Promise<Response> {
  assertCurrentChat(pending, signal);
  let response: Response;
  try {
    response = await fetch(path, {
      method: 'POST',
      credentials: 'same-origin',
      signal,
      headers: { ...authHeaders(), 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(payload),
    });
  } catch (reason) {
    assertCurrentChat(pending, signal);
    if (signal.aborted) throw reason;
    throw new Error('网络没有连上，本轮问题与附图已保留，请继续原来这一轮');
  }
  assertCurrentChat(pending, signal);
  if (response.status === 401) {
    requireLogin();
    throw new Error('请登录后继续');
  }
  if (!response.ok) {
    throw new Error(response.status === 409 ? '内容已在别处更新，刷新后核对' : '本轮没有连上，请继续原来这一轮');
  }
  return response;
}
export async function consumeV3(response: Response, accept: (event: ChatEvent) => void, signal?: AbortSignal) {
  await readSse(
    response,
    (frame) => {
      if (frame.data === '[DONE]') return;
      const event = chatEvent(JSON.parse(frame.data));
      if (event) accept(event);
    },
    signal,
  );
}
function delay(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const done = () => {
      signal.removeEventListener('abort', abort);
      resolve();
    };
    const timer = setTimeout(done, 2000);
    function abort() {
      clearTimeout(timer);
      signal.removeEventListener('abort', abort);
      reject(signal.reason);
    }
    signal.addEventListener('abort', abort, { once: true });
  });
}
export async function recoverV3(pending: PendingChat, accept: (event: ChatEvent) => void, signal: AbortSignal) {
  for (let attempt = 0; attempt < 90; attempt++) {
    assertCurrentChat(pending, signal);
    const run = await api<Run>(`/api/runs/${encodeURIComponent(pending.runId)}`, { signal });
    assertCurrentChat(pending, signal);
    if (run.status === 'succeeded') {
      const event = chatEvent({ type: 'result', result: run.result });
      if (!event) throw new Error('没有收到完整回答，请保留本轮并稍后核对');
      accept(event);
      return;
    }
    if (!['queued', 'running'].includes(run.status)) throw new Error(run.error || '本轮已停止，可继续原来这一轮');
    accept({ type: 'status', text: '连接波动，正在查找本轮已保存的结果…' });
    await delay(signal);
  }
  throw new Error('本轮仍在后台处理，请稍后继续原来这一轮或从历史查看');
}
export async function executeV3(
  pending: PendingChat,
  retry: boolean,
  accept: (event: ChatEvent) => void,
  signal: AbortSignal,
) {
  assertCurrentChat(pending, signal);
  let response: Response | undefined,
    completed = false,
    serverError = '';
  const receive = (event: ChatEvent) => {
    assertCurrentChat(pending, signal);
    if (event.type === 'started') {
      pending.runId = event.run_id;
      storePending(pending);
    }
    if (event.type === 'final') completed = true;
    if (event.type === 'error') serverError = event.message;
    accept(event);
  };
  if (retry) {
    let run: Run | undefined;
    try {
      run = await api<Run>(`/api/runs/${encodeURIComponent(pending.runId)}`, { signal });
    } catch (error) {
      if (object(error).status !== 404 || pending.restoreOnly) throw error;
    }
    assertCurrentChat(pending, signal);
    if (run?.status === 'succeeded') {
      const event = chatEvent({ type: 'result', result: run.result });
      if (!event) throw new Error('没有收到完整回答，请保留本轮并稍后核对');
      receive(event);
      return;
    }
    if (run && ['running', 'queued'].includes(run.status)) return recoverV3(pending, receive, signal);
    if (run && !['failed', 'stale'].includes(run.status)) throw new Error('本轮已停止，请明确开始新一轮');
    if (run)
      response = await streamRequest(
        `/api/runs/${encodeURIComponent(run.id)}/retry`,
        { request_id: `retry:${run.operation_id}` },
        pending,
        signal,
      );
  }
  if (!response)
    response = pending.resume
      ? await streamRequest(
          `/api/runs/${encodeURIComponent(pending.resume.runId)}/resume`,
          {
            interrupt_id: pending.resume.interrupt_id,
            state_version: pending.resume.state_version,
            message_id: pending.resume.message_id,
            message: pending.payload.message,
          },
          pending,
          signal,
        )
      : await streamRequest('/api/chat', pending.payload, pending, signal);
  try {
    await consumeV3(response, receive, signal);
  } catch (error) {
    assertCurrentChat(pending, signal);
    if (signal.aborted || serverError) throw error;
  }
  if (serverError) throw new Error(serverError);
  if (!completed) await recoverV3(pending, receive, signal);
}
