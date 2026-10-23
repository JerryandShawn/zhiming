import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider, type InfiniteData } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Chat from '../src/live/Chat';
import { operationNamespace, useAuth } from '../src/api/client';
import { loadPending, newPending, readDraft, saveDraft } from '../src/chat/storage';
import type { HistoryRow } from '../src/chat/types';

const firstPage = '/api/history?limit=20&before=';
const retryButton = () => screen.getByRole('button', { name: '重新读取历史对话' });
const composer = () => screen.getByRole('textbox', { name: '和明镜说说' });
const clients: QueryClient[] = [];
function gate<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
}
function historyRow(id: string, content: string): HistoryRow {
  return {
    role: 'assistant',
    content,
    at: '2026-10-21T00:00:00+08:00',
    source: 'web',
    cursor: id,
    turn_id: `turn-${id}`,
  };
}
function unavailable() {
  return Response.json({ detail: 'PRIVATE_BACKEND_DIAGNOSTIC' }, { status: 503 });
}
function mount(cached?: HistoryRow[]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, gcTime: Infinity } },
  });
  clients.push(client);
  if (cached)
    client.setQueryData<InfiniteData<HistoryRow[]>>(['chat', 'history', operationNamespace()], {
      pages: [cached],
      pageParams: [''],
    });
  return {
    ...render(
      <QueryClientProvider client={client}>
        <Chat />
      </QueryClientProvider>,
    ),
    client,
  };
}
function historyTransport(...responses: (Response | Promise<Response>)[]) {
  let index = 0;
  const fetcher = vi.fn((path: string, init?: RequestInit) => {
    if (!path.startsWith('/api/history?') || (init?.method && init.method !== 'GET'))
      throw new Error('Unexpected non-history operation');
    const response = responses[index++];
    if (!response) throw new Error('Unexpected extra history read');
    return Promise.resolve(response);
  });
  vi.stubGlobal('fetch', fetcher);
  return fetcher;
}
function assertHistoryGetOnly(fetcher: ReturnType<typeof historyTransport>, paths: string[]) {
  expect(fetcher.mock.calls.map(([path]) => path)).toEqual(paths);
  for (const [, options] of fetcher.mock.calls) {
    expect(options?.method ?? 'GET').toBe('GET');
    expect(options?.body).toBeUndefined();
  }
}
beforeEach(() => {
  sessionStorage.clear();
  useAuth.getState().setToken(`synthetic-history-${crypto.randomUUID()}`);
  window.history.replaceState(null, '', '#/chat');
});
afterEach(() => {
  cleanup();
  for (const client of clients.splice(0)) client.clear();
  vi.unstubAllGlobals();
});

describe('manual chat history GET retry', () => {
  it('shows a loading action, blocks duplicate reads and preserves edits made while retrying', async () => {
    const waiting = gate<Response>(),
      fetcher = historyTransport(unavailable(), waiting.promise);
    mount();
    await screen.findByRole('button', { name: '重新读取历史对话' });
    fireEvent.change(composer(), { target: { value: '尚未发送的草稿' } });
    const button = retryButton();
    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByText('正在重新读取历史对话…')).toBeVisible();
    fireEvent.change(composer(), { target: { value: '重读期间继续写的草稿' } });
    await act(async () => {
      waiting.resolve(Response.json([historyRow('loaded', '重新读到的历史回答')]));
      await waiting.promise;
    });
    expect(await screen.findByText('重新读到的历史回答')).toBeVisible();
    expect(screen.queryByRole('button', { name: '重新读取历史对话' })).not.toBeInTheDocument();
    expect(composer()).toHaveValue('重读期间继续写的草稿');
    expect(readDraft()).toBe('重读期间继续写的草稿');
    expect(loadPending()).toBeUndefined();
    assertHistoryGetOnly(fetcher, [firstPage, firstPage]);
  });

  it('keeps already displayed confirmed history visible during a failed background read and manual retry', async () => {
    const saved = historyRow('saved', '已经显示的历史回答'),
      added = historyRow('added', '新读到的历史回答');
    const waiting = gate<Response>(),
      fetcher = historyTransport(unavailable(), waiting.promise);
    mount([saved]);
    expect(screen.getByText(saved.content)).toBeVisible();
    await screen.findByRole('button', { name: '重新读取历史对话' });
    fireEvent.click(retryButton());
    expect(screen.getByText(saved.content)).toBeVisible();
    await act(async () => {
      waiting.resolve(Response.json([saved, added]));
      await waiting.promise;
    });
    expect(await screen.findByText(added.content)).toBeVisible();
    expect(screen.getByText(saved.content)).toBeVisible();
    assertHistoryGetOnly(fetcher, [firstPage, firstPage]);
  });

  it('does not resume a pending turn, resend attachments or alter its saved request while retrying history', async () => {
    const pending = newPending('尚未完成的合成问题', ['data:image/png;base64,c3ludGhldGlj']);
    saveDraft('继续编辑但未发送');
    const fetcher = historyTransport(unavailable(), Response.json([]));
    mount();
    await screen.findByRole('button', { name: '重新读取历史对话' });
    expect(screen.getByRole('button', { name: '继续原来这一轮' })).toBeVisible();
    fireEvent.click(retryButton());
    await waitFor(() => expect(screen.queryByRole('button', { name: '重新读取历史对话' })).not.toBeInTheDocument());
    expect(loadPending()).toEqual(pending);
    expect(composer()).toHaveValue('继续编辑但未发送');
    expect(readDraft()).toBe('继续编辑但未发送');
    expect(screen.getByRole('list', { name: '本轮附图' })).toHaveTextContent('附图 1');
    assertHistoryGetOnly(fetcher, [firstPage, firstPage]);
  });

  it('keeps the retry available after another failure and never exposes raw backend details', async () => {
    const fetcher = historyTransport(
      unavailable(),
      unavailable(),
      Response.json([historyRow('recovered', '稍后恢复的历史')]),
    );
    mount();
    await screen.findByRole('button', { name: '重新读取历史对话' });
    fireEvent.change(composer(), { target: { value: '多次失败也保留的草稿' } });
    fireEvent.click(retryButton());
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(retryButton()).not.toBeDisabled());
    expect(screen.getByText('历史暂时没有读取完整，可以稍后重试。')).toBeVisible();
    expect(document.body).not.toHaveTextContent('PRIVATE_BACKEND_DIAGNOSTIC');
    fireEvent.click(retryButton());
    expect(await screen.findByText('稍后恢复的历史')).toBeVisible();
    expect(composer()).toHaveValue('多次失败也保留的草稿');
    assertHistoryGetOnly(fetcher, [firstPage, firstPage, firstPage]);
  });

  it('preserves a locally completed turn and sends no additional conversation request on history retry', async () => {
    const waiting = gate<Response>();
    let historyCalls = 0,
      chatPosts = 0;
    const fetcher = vi.fn((path: string, init?: RequestInit) => {
      if (path === firstPage && !init?.method) {
        historyCalls++;
        return historyCalls === 1
          ? Promise.resolve(Response.json([]))
          : historyCalls === 2
            ? Promise.resolve(unavailable())
            : waiting.promise;
      }
      // One explicitly scripted setup turn drives the actual useChat reducer;
      // retry below must not issue another POST, resume or model request.
      if (path === '/api/chat' && init?.method === 'POST' && ++chatPosts === 1)
        return Promise.resolve(
          new Response(
            'data: {"type":"started","run_id":"synthetic-completed-run"}\n\ndata: {"type":"result","result":{"answer":"本机脚本已完成的回答"}}\n\ndata: [DONE]\n\n',
            { headers: { 'Content-Type': 'text/event-stream' } },
          ),
        );
      throw new Error('Unexpected conversation retry or non-history route');
    });
    vi.stubGlobal('fetch', fetcher);
    const { client } = mount();
    await waitFor(() => expect(client.isFetching()).toBe(0));
    fireEvent.change(composer(), { target: { value: '已完成的合成问题' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    expect(await screen.findByText('本机脚本已完成的回答')).toBeVisible();
    await screen.findByRole('button', { name: '重新读取历史对话' });
    await waitFor(() => expect(loadPending()).toBeUndefined());
    fireEvent.change(composer(), { target: { value: '留给下一轮的草稿' } });
    const postsBefore = fetcher.mock.calls.filter(([, init]) => init?.method === 'POST').length;
    fireEvent.click(retryButton());
    expect(screen.getByText('本机脚本已完成的回答')).toBeVisible();
    await act(async () => {
      waiting.resolve(Response.json([]));
      await waiting.promise;
    });
    await waitFor(() => expect(screen.queryByRole('button', { name: '重新读取历史对话' })).not.toBeInTheDocument());
    expect(screen.getByText('已完成的合成问题')).toBeVisible();
    expect(screen.getByText('本机脚本已完成的回答')).toBeVisible();
    expect(composer()).toHaveValue('留给下一轮的草稿');
    expect(readDraft()).toBe('留给下一轮的草稿');
    expect(postsBefore).toBe(1);
    expect(fetcher.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(postsBefore);
    expect(fetcher.mock.calls.every(([path]) => path === firstPage || path === '/api/chat')).toBe(true);
  });

  it('does not cancel a manual retry to fetch an older page, then permits pagination after completion', async () => {
    const rows = Array.from({ length: 20 }, (_, index) => historyRow(`saved-${index}`, `已保存历史 ${index}`));
    const waiting = gate<Response>(),
      fetcher = historyTransport(unavailable(), waiting.promise, Response.json([]));
    mount(rows);
    await screen.findByRole('button', { name: '重新读取历史对话' });
    const older = screen.getByRole('button', { name: '查看更早对话' });
    fireEvent.click(retryButton());
    expect(older).toBeDisabled();
    fireEvent.click(older);
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls[1][1]?.signal?.aborted).toBe(false);
    expect(screen.getByText(rows[0].content)).toBeVisible();
    await act(async () => {
      waiting.resolve(Response.json(rows));
      await waiting.promise;
    });
    await waitFor(() => expect(older).not.toBeDisabled());
    fireEvent.click(older);
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(screen.queryByRole('button', { name: '查看更早对话' })).not.toBeInTheDocument());
    expect(screen.getByText(rows[0].content)).toBeVisible();
    assertHistoryGetOnly(fetcher, [firstPage, firstPage, `${firstPage}saved-0`]);
  });
});
